import json
import re
import httpx
from fastapi import HTTPException, status
from saraswati_tenant import current_school

from app.core.config import settings
from app.models.class_master import ClassMaster

_TIMEOUT = 60.0

# Reading a stack of scanned sheets, or planning a whole subject's year, both
# run well past a single answer's worth of work.
_SCAN_TIMEOUT = 300.0

# State and CBSE set different question patterns, so every generation call has
# to carry the board. One process now serves every school, and the two schools
# on it do not share a board — SGS is CBSE, SSS follows AP SCERT — so a single
# configured value would be wrong for one of them on every paper it generated.
#
# Read from the school this request resolved to, the same way schoolName is.
# settings.SCHOOL_BOARD stays as the fallback: a single-school deployment has
# no tenant config to read, and a tenant whose config predates this key should
# keep working rather than send the AI something it does not understand.
_BOARDS = ("State", "CBSE")


def _school_board() -> str:
    """The board for the school this request belongs to."""
    try:
        board = (current_school().config or {}).get("board")
    except Exception:
        # No school resolved — a background job, or a single-school deployment
        # with no tenant middleware in front of it.
        board = None
    return board if board in _BOARDS else settings.SCHOOL_BOARD



# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_info(teacher) -> dict:
    return {
        "id": teacher.teacher_id,
        "name": teacher.full_name or "",
        "email": teacher.email_id or "",
        "role": "Teacher",
    }


def _client_name() -> str:
    """
    The `client_name` the AI service logs token usage against.

    One process serves several schools, so this is read from the school the
    request resolved to and not from .env. A tenant that has not been given an
    `aiClientName` falls back to the configured default.
    """
    try:
        name = (current_school().config or {}).get("aiClientName")
    except Exception:
        # No school resolved — a background job, or a single-school
        # deployment with no tenant middleware in front of it.
        name = None
    return name or settings.AI_CLIENT_NAME


def _caller(teacher) -> dict:
    """
    The two fields every /api/faculty/* endpoint expects.

    `user_email` is required by the service on every call — it is what token
    usage is billed against, so a teacher with no email on their record would
    be rejected with a 422 that says nothing useful. Fail here instead.
    """
    email = (teacher.email_id or "").strip()
    if not email:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This teacher record has no email address, and the AI service "
            "requires one. Add an email to the teacher before using AI features.",
        )
    return {"user_email": email, "client_name": _client_name()}


def _ai_error(e: Exception):
    if isinstance(e, httpx.TimeoutException):
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI service timed out")
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.json()
            detail = body.get("details") or body.get("error") or body.get("message") or "AI service error"
        except Exception:
            detail = "AI service error"
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI service unreachable")


# Section headings exactly as the AI service emits them, in the order they
# appear on the school's printed lesson-plan form.
_SECTIONS: list[tuple[str, str]] = [
    ("objectives",  "Learning objectives"),
    ("outcomes",    "Learning outcomes"),
    ("methodology", "Methodology"),
    ("tlm",         "TLM"),
    ("activities",  "Activities"),
    ("assessment",  "Assessment"),
    ("homework",    "Home Work"),
]

_ANY_HEADING = "|".join(re.escape(h) for _, h in _SECTIONS)

_ITEM_MARKER = re.compile(r'^(?:\d+[.)]|[-•*])\s+')


def _extract_section(text: str, heading: str) -> str:
    """
    Return the block under a `Heading:` line, up to the next known heading,
    the signature line, or end of text.

    The AI writes headings bare at the start of a line and numbers the items
    beneath them, so the heading itself is never numbered.
    """
    pattern = (
        rf'^[ \t]*{re.escape(heading)}[ \t]*:[ \t]*$\n'
        rf'(.*?)'
        rf'(?=^[ \t]*(?:{_ANY_HEADING})[ \t]*:[ \t]*$|^[ \t]*Sign\.|\Z)'
    )
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


def _bullets(block: str) -> list[str]:
    """
    Split a block into its numbered or bulleted items.

    A line without a marker continues the item above it, so an item that wraps
    across lines stays one item. A block with no markers at all (Home Work is
    written as a paragraph) comes back as a single item.
    """
    items: list[str] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _ITEM_MARKER.match(line):
            items.append(_ITEM_MARKER.sub('', line).strip())
        elif items:
            items[-1] = f"{items[-1]} {line}"
        else:
            items.append(line)
    return [i for i in items if i]


_SECTION_TOKEN = re.compile(r"^[A-Za-z]{1,2}\d?$")   # A, B, A1, AB — not "10"


def _split_class_section(value: str) -> tuple[str, str]:
    """
    "Class 8 A" → ("Class 8", "A");  "8th Grade - A" → ("8th Grade", "A");
    "Class 10"  → ("Class 10", "")   — a trailing number is the class, not a section.
    """
    text = value.strip()
    level, _, last = text.rpartition(" ")
    if level and _SECTION_TOKEN.match(last):
        return level.rstrip(" -").strip(), last
    return text, ""


def _class_name(teacher, db=None) -> str:
    """
    The class as a person says it — `8th Grade`, not `Class 32`.

    class_id is a primary key, not a class. Using it directly printed headers
    like "Class 32 A" on a document the teacher hands over, 32 being the row
    number of their class in class_master, and told the AI the grade level was
    "Class 32" — so the plan came back pitched at no real year group. The name
    lives in class_master.class_name, resolved here the way marks_service
    already does it.

    Without a session there is nothing to resolve against, so fall back to the
    old shape rather than printing a bare id with no label at all.
    """
    if not teacher.class_id:
        return ""
    if db is not None:
        row = (
            db.query(ClassMaster)
            .filter(ClassMaster.class_id == teacher.class_id)
            .first()
        )
        name = (row.class_name or "").strip() if row else ""
        if name:
            return name
    return f"Class {teacher.class_id}"


def _class_section(teacher, db=None) -> str:
    """`8th Grade A` — the two columns the form prints as one field."""
    parts = [p for p in (_class_name(teacher, db), teacher.section_1) if p]
    return " ".join(parts)


def _parse_lesson_plan(raw_text: str, header: dict, teacher) -> dict:
    """
    Convert the AI service's plain-text lesson plan into the structured dict
    the printable form renders.

    The AI echoes a header block above `Learning objectives:` — teacher name,
    designation, dates. That block is ignored. Those facts are ours: we know
    who is logged in and what they asked for, and the AI has been observed
    filling them with "Not specified" or inventing a designation. Only the
    seven teaching sections are read out of the text.
    """
    sections = {key: _bullets(_extract_section(raw_text, heading))
                for key, heading in _SECTIONS}

    return {
        "title": f"Lesson Plan: {header['chapter']}" if header["chapter"] else "Lesson Plan",
        "header": header,
        "sections": sections,
        # Legacy top-level keys, kept so plans saved by the previous version
        # and any frontend still reading them keep rendering.
        "chapter_text": header["chapter"],
        "duration_minutes": header["no_of_periods"],
        "class_name": str(teacher.class_id or ""),
        "section": teacher.section_1 or "",
        "subject": header["subject"],
        "objectives": sections["objectives"],
        "homework": "\n".join(sections["homework"]),
    }


# ── Internal chat caller ─────────────────────────────────────────────────────

async def _chat(message: str, target_language: str, teacher) -> str:
    """Call Node.js /api/v1/ai/teacher/chat and return the reply text."""
    payload = {
        "message": message,
        "targetLanguage": target_language,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/chat",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("reply") or data.get("message") or data.get("response") or ""
    except Exception as e:
        _ai_error(e)


# ── Public functions ──────────────────────────────────────────────────────────

async def generate_lesson_plan(req, teacher, db=None) -> dict:
    """
    `req` is a LessonPlanGenerateRequest. Header fields fall back to the
    teacher's own record, so the frontend only has to send what was overridden
    on the form.

    `db` is needed only to turn the teacher's class_id into the class name for
    the header, and is optional so existing callers keep working.
    """
    header = {
        # The school is whichever one this request resolved to, not a value
        # from .env — one process now serves every school, so a configured
        # name would print the wrong masthead on all but one of them.
        "school_name":          req.schoolName or current_school().config.get("schoolName", ""),
        "teacher_name":         teacher.full_name or "",
        "designation":          req.designation or teacher.role or "Teacher",
        "class_section":        req.classSection or _class_section(teacher, db),
        "subject":              req.subject or teacher.subject_name or "",
        "chapter":              req.chapter,
        "no_of_periods":        req.noOfPeriods,
        "date_of_commencement": req.dateOfCommencement.isoformat() if req.dateOfCommencement else "",
        "expected_completion":  req.expectedCompletion.isoformat() if req.expectedCompletion else "",
        # Filled in after the lesson is taught, via PATCH — never at generation.
        "actual_completion":    "",
    }

    # The AI writes the plan body from this. Class, section, subject, designation
    # and dates are what its prompt prints; without them it reads "Not specified"
    # and the plan comes back pitched at no class in particular. The AI service
    # wants class and section as separate fields; the teacher record already has
    # them apart, and a form override ("Class 8 A") is split on its last space.
    if req.classSection:
        level, section = _split_class_section(req.classSection)
    else:
        level = _class_name(teacher, db)
        section = teacher.section_1 or ""

    def _or_unspecified(v):
        # Her handler defaults absent fields to this; sending "" would print "".
        return v or "Not specified"

    payload = {
        # Required by the service.
        "topic": req.chapter,
        "grade_level": _or_unspecified(level),
        # Optional, but each one it does not get prints "Not specified" on the
        # plan, so send everything the teacher record or the form can supply.
        "syllabus": _school_board(),
        "subject": _or_unspecified(header["subject"]),
        "teacher_name": header["teacher_name"],
        "designation": _or_unspecified(header["designation"]),
        "section": _or_unspecified(section),
        "no_of_periods": str(req.noOfPeriods or ""),
        "date_of_commencement": _or_unspecified(header["date_of_commencement"]),
        "expected_completion": _or_unspecified(header["expected_completion"]),
        # Filled in after the lesson is taught, via PATCH — never at generation.
        "actual_completion": "",
        **_caller(teacher),
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/faculty/generate-material",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            # The plan body arrives under response.teaching_material. The older
            # service returned it as `lessonPlan`; both are read so a rollback
            # of the AI service does not take this endpoint down with it.
            raw_text = (
                (data.get("response") or {}).get("teaching_material")
                or data.get("teaching_material")
                or data.get("lessonPlan")
                or ""
            )
            return _parse_lesson_plan(raw_text, header, teacher)
    except Exception as e:
        _ai_error(e)


def _with_questions(body):
    """
    Lift the generated questions to the top level, whatever they arrived in.

    The service answers {"status": "success", "question_paper": {...}}, so the
    list sits two levels down. The review screen looks for an array under
    `questions`, `data`, `questionPaper`, `question_paper` or `items` — all at
    the top level — finds an object rather than an array, and treats the paper
    as ungenerated: every slot renders "Not generated by AI yet" even though
    the questions came back fine and the request logged 200.

    `question_paper` is also sometimes the paper as plain text rather than a
    structure, which the screen prints as-is. That case must keep working, so
    nothing is removed here — `questions` is only *added*, and only when a
    list is actually found.
    """
    if not isinstance(body, dict):
        return body
    if isinstance(body.get("questions"), list):
        return body

    paper = body.get("question_paper")
    if isinstance(paper, str):
        try:
            paper = json.loads(paper)
        except (ValueError, TypeError):
            return body          # the plain-text paper; leave it alone

    found = None
    if isinstance(paper, list):
        found = paper
    elif isinstance(paper, dict):
        for key in ("questions", "items", "data"):
            if isinstance(paper.get(key), list):
                found = paper[key]
                break

    return {**body, "questions": found} if found is not None else body


# The service names the question mix it understands; anything else makes it
# fall back to a mixed paper silently, which looks like the filter was ignored.
_FORMAT_TYPES = ("all", "mcq", "true_false", "short", "fill")


def _format_type(question_type: str | None) -> str:
    if not question_type:
        return "all"
    key = question_type.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "multiple_choice": "mcq",
        "mcqs": "mcq",
        "truefalse": "true_false",
        "fill_in_the_blanks": "fill",
        "fill_in_blank": "fill",
        "short_answer": "short",
    }
    key = aliases.get(key, key)
    return key if key in _FORMAT_TYPES else "all"


async def generate_question_paper(
    topics: list[str],
    difficulty: str,
    total_marks: int,
    teacher,
    question_type: str | None = None,
    num_questions: int | None = None,
) -> dict:
    """
    `topics` are chapter *names*, not ids.

    The service scopes generation to the topics it is given, so the caller
    resolves ids to names first. It used to take a single chapterId, which is
    why a paper spanning several chapters could only ever send the first one.

    `num_questions` is how many questions the blueprint asks for. The service
    has always accepted it and we never sent it, so the length of a paper was
    inferred from the marks alone — which is why a 50-mark paper came back
    with an arbitrary number of questions regardless of what the teacher had
    laid out on the Configure screen.
    """
    payload = {
        "topics": topics,
        "difficulty": difficulty,
        "total_marks": total_marks,
        "format_type": _format_type(question_type),
        # State and CBSE set different question patterns for the same chapter.
        # Without this the AI was never told which, and answered from the
        # chapter text alone — whichever textbook happened to be uploaded
        # decided the pattern, with nothing stating it anywhere.
        "syllabus": _school_board(),
        **_caller(teacher),
    }
    # Omitted rather than sent as null when the caller has no blueprint, so
    # the service keeps its own default instead of reading a null as zero.
    if num_questions:
        payload["num_questions"] = num_questions
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/faculty/generate-exam",
                json=payload,
            )
            r.raise_for_status()
            return _with_questions(r.json())
    except Exception as e:
        _ai_error(e)


async def generate_competitive_paper(req, teacher) -> dict:
    """
    A competitive paper — NMMS, an olympiad, a scholarship test.

    The AI service has one paper endpoint, so this is that same call with the
    pattern attached, not a second service. Everything the Configure screen
    collected is forwarded: the service reads the fields it knows and ignores
    the rest, which is what lets the screen ship ahead of the generator.

    totalMarks is deliberately not checked here. The service accepts a fixed
    set of totals and answers "Total marks must be valid." for anything else,
    and _ai_error passes that message straight through to the teacher. One
    rule, living in the service that owns it, rather than a copy here that
    goes stale the day they widen it.
    """
    payload = {
        # What the service reads today.
        "chapterId": req.chapterId if req.chapterId is not None
                     else (req.chapterIds[0] if req.chapterIds else None),
        "difficulty": req.difficulty,
        "totalMarks": req.totalMarks,
        "questionType": req.questionType,
        "syllabus": _school_board(),
        "userInfo": _user_info(teacher),

        # The competitive pattern. Accepted by the service and, as far as we
        # can tell from the outside, ignored by it today — an unknown field
        # does not make it complain. Sent anyway, so the papers start
        # following the pattern the day it reads them, with nothing to change
        # on this side.
        "examType": req.examType,
        "examTarget": req.examTarget,
        "chapterIds": req.chapterIds,
        "classLevel": req.classLevel,
        "subject": req.subject,
        "difficultyMix": req.difficultyMix,
        "blueprint": req.blueprint,
        "minutes": req.minutes,
        "negativeMarking": req.negativeMarking,
        "questionCount": req.questionCount,
        "marksEach": req.marksEach,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/question-paper",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def correct_answer(
    question: str,
    student_answer: str,
    max_marks: int,
    rubric: str,
    teacher,
) -> dict:
    # The service takes no max_marks on this endpoint — the ceiling belongs in
    # the rubric, so it is stated there when the caller did not write one.
    payload = {
        "question": question,
        "student_answer": student_answer,
        "rubric": rubric or f"Mark out of {max_marks}.",
        **_caller(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/faculty/auto-correct",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def scan_answer_sheets(
    answer_sheets: list[tuple[str, bytes, str]],
    teacher,
    mode: str = "direct_grade",
    question_paper_file: tuple[str, bytes, str] | None = None,
    question_paper_json: str | None = None,
    rubric_or_answer_key: str | None = None,
    subject: str | None = None,
    class_level: str | None = None,
    max_marks: int | None = None,
    student_name: str | None = None,
    roll_number: str | None = None,
) -> dict:
    """
    Read and mark scanned answer sheets.

    `answer_sheets` is a list of (filename, content, content_type). This
    endpoint is multipart/form-data, not JSON like the rest of the service —
    the sheets are uploaded files.

    Scanning a whole paper takes far longer than a single answer, so this call
    gets its own timeout rather than the service-wide one.

    `question_paper_file` is the official paper, scanned or digital. It is sent
    as a file rather than only as question_paper_json because the JSON is
    produced by a *text* extractor: a photographed or scanned question paper
    yields nothing from it, and then the marker has no reference at all. It
    also tells the marker how the questions are numbered — an answer sheet
    written as "Section B, 1, 2" has to be matched to questions 3 and 4 of the
    paper, and without the paper those numbers collide.
    """
    files = [("answer_sheets", (name, blob, ctype)) for name, blob, ctype in answer_sheets]
    if question_paper_file is not None:
        name, blob, ctype = question_paper_file
        files.append(("question_paper_file", (name, blob, ctype)))

    data = {"mode": mode, **_caller(teacher)}
    for key, value in (
        ("question_paper_json", question_paper_json),
        ("rubric_or_answer_key", rubric_or_answer_key),
        ("subject", subject),
        ("class_level", class_level),
        ("max_marks", max_marks),
        ("student_name", student_name),
        ("roll_number", roll_number),
    ):
        if value is not None and value != "":
            data[key] = str(value)

    try:
        async with httpx.AsyncClient(timeout=_SCAN_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/faculty/auto-correct/scan",
                data=data,
                files=files,
            )
            r.raise_for_status()
            body = r.json()

            # The service wraps the whole result in `evaluation`, with only
            # `status` beside it:
            #
            #   {"status": "success",
            #    "evaluation": {"student_details": …, "summary": …,
            #                   "questions": [...]}}
            #
            # The field names inside are the ones the screen reads; it was the
            # extra level that broke it. Returned flat so callers see
            # student_details / summary / questions at the top, which is what
            # the integration note asks the gateway to do.
            #
            # Falls back to the body itself rather than assuming the wrapper:
            # the service declares this response as untyped `{}` in its
            # OpenAPI, so nothing but this code would catch the shape changing
            # back.
            evaluation = body.get("evaluation") if isinstance(body, dict) else None
            return evaluation if isinstance(evaluation, dict) and evaluation else body
    except Exception as e:
        _ai_error(e)


async def academic_planner(
    grade_level: str,
    subject: str,
    teacher,
    chapters: list[str] | None = None,
    total_chapters: int | None = None,
    academic_year: str | None = None,
    total_teaching_periods: int | None = None,
) -> dict:
    """A subject's chapters mapped onto the four-exam academic calendar."""
    payload = {
        "grade_level": grade_level,
        "subject": subject,
        "syllabus": _school_board(),
        **_caller(teacher),
    }
    if chapters:
        payload["chapters"] = chapters
    if total_chapters is not None:
        payload["total_chapters"] = total_chapters
    if academic_year:
        payload["academic_year"] = academic_year
    if total_teaching_periods is not None:
        payload["total_teaching_periods"] = total_teaching_periods

    try:
        async with httpx.AsyncClient(timeout=_SCAN_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/faculty/academic-planner",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def get_assignment_reminders(teacher) -> dict:
    payload = {"userInfo": _user_info(teacher)}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/assignment-reminders",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def get_completion_alerts(teacher) -> dict:
    payload = {"userInfo": _user_info(teacher)}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/completion-alerts",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def virtual_slate(raw_text: str, action: str, teacher) -> dict:
    payload = {
        "rawText": raw_text,
        "action": action,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/virtual-slate",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def student_analytics(student_name: str, subject: str, teacher) -> dict:
    payload = {
        "studentName": student_name,
        "subject": subject,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/student-analytics",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def class_analytics(subject: str, teacher) -> dict:
    payload = {
        "subject": subject,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/class-analytics",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def translate_text(text: str, target_language: str, teacher) -> dict:
    # Was /api/v1/ai/teacher/translate, which 404s: that whole prefix belonged
    # to the old service and is gone. The live route also renames the field —
    # target_language, not targetLanguage — and takes the caller as two flat
    # fields instead of a userInfo object.
    payload = {
        "text": text,
        "target_language": target_language,
        **_caller(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/faculty/translate",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def translate_audio(audio_file: str, target_language: str, teacher) -> dict:
    payload = {
        "audioFile": audio_file,
        "targetLanguage": target_language,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/audio-translate",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def speech_to_text(audio_file: str, language: str, teacher) -> dict:
    payload = {
        "audioFile": audio_file,
        "language": language,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/speech-to-text",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def text_to_speech(text: str, language: str, voice: str, teacher) -> dict:
    """
    Read text aloud.

    Was /api/v1/ai/teacher/speak, which 404s — that whole prefix is gone.

    `voice` is still accepted from the screen but is not forwarded: the
    /api/faculty/text-to-voice contract has no voice field, so the service
    picks its own. Sending it anyway would be rejected as an unknown field on
    a schema that validates strictly. The parameter is kept rather than
    removed so the screen's Male/Female choice keeps working as a no-op
    instead of becoming a 422, and so it is one line to forward again if a
    voice field is added.
    """
    payload = {
        "text": text,
        "language": language,
        **_caller(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/faculty/text-to-voice",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)


async def content_search(subject: str, keyword: str, teacher) -> dict:
    payload = {
        "subject": subject,
        "keyword": keyword,
        "teacherId": teacher.teacher_id,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/content-search",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        _ai_error(e)
