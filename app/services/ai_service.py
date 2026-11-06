import re
import re
import httpx
from fastapi import HTTPException, status
from saraswati_tenant import current_school

from app.core.config import settings

_TIMEOUT = 60.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_info(teacher) -> dict:
    return {
        "id": teacher.teacher_id,
        "name": teacher.full_name or "",
        "email": teacher.email_id or "",
        "role": "Teacher",
    }


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


def _class_section(teacher) -> str:
    """`Class 8 A` — the two columns the form prints as one field."""
    parts = []
    if teacher.class_id:
        parts.append(f"Class {teacher.class_id}")
    if teacher.section_1:
        parts.append(teacher.section_1)
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

async def generate_lesson_plan(req, teacher) -> dict:
    """
    `req` is a LessonPlanGenerateRequest. Header fields fall back to the
    teacher's own record, so the frontend only has to send what was overridden
    on the form.
    """
    header = {
        # The school is whichever one this request resolved to, not a value
        # from .env — one process now serves every school, so a configured
        # name would print the wrong masthead on all but one of them.
        "school_name":          req.schoolName or current_school().config.get("schoolName", ""),
        "teacher_name":         teacher.full_name or "",
        "designation":          req.designation or teacher.role or "Teacher",
        "class_section":        req.classSection or _class_section(teacher),
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
        level = f"Class {teacher.class_id}" if teacher.class_id else ""
        section = teacher.section_1 or ""

    def _or_unspecified(v):
        # Her handler defaults absent fields to this; sending "" would print "".
        return v or "Not specified"

    payload = {
        "chapterId": req.chapterId,
        "topic": req.chapter,
        "noOfPeriods": req.noOfPeriods,
        # Kept for the AI service's current handler, which still reads it.
        "durationMinutes": req.noOfPeriods * settings.PERIOD_MINUTES,
        "classLevel": _or_unspecified(level),
        "section": _or_unspecified(section),
        "subject": _or_unspecified(header["subject"]),
        "designation": _or_unspecified(header["designation"]),
        "dateOfCommencement": _or_unspecified(header["date_of_commencement"]),
        "expectedCompletion": _or_unspecified(header["expected_completion"]),
        "actualCompletion": "",
        "userInfo": _user_info(teacher),
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/lesson-plan",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            raw_text = data.get("lessonPlan", "")
            return _parse_lesson_plan(raw_text, header, teacher)
    except Exception as e:
        _ai_error(e)


async def generate_question_paper(
    chapter_id: int,
    difficulty: str,
    total_marks: int,
    teacher,
    question_type: str | None = None,
) -> dict:
    payload = {
        "chapterId": chapter_id,
        "difficulty": difficulty,
        "totalMarks": total_marks,
        "questionType": question_type,
        "userInfo": _user_info(teacher),
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
    payload = {
        "question": question,
        "studentAnswer": student_answer,
        "maxMarks": max_marks,
        "rubric": rubric,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/correct-answer",
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
    payload = {
        "text": text,
        "targetLanguage": target_language,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/translate",
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
    payload = {
        "text": text,
        "language": language,
        "voice": voice,
        "userInfo": _user_info(teacher),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/ai/teacher/speak",
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
