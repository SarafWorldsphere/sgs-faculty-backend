"""
Question papers — generate with the AI, then keep the ones worth keeping.

  POST   /question-papers/generate               ask the AI for a school paper (not stored)
  POST   /question-papers/generate-competitive   the same, for a competitive pattern
  POST   /question-papers            save a generated paper
  GET    /question-papers            the teacher's saved papers, newest first
  GET    /question-papers/{id}       one saved paper, full content
  DELETE /question-papers/{id}       soft delete (record_status = Deleted)

Saved papers are the source for printing and for assigning a test later.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher
from app.db.session import get_db
from app.models.chapter_master import ChapterMaster
from app.models.question_paper import TeacherQuestionPaper
from app.models.teacher import TeacherMaster
from app.services.ai_service import generate_competitive_paper, generate_question_paper

router = APIRouter(prefix="/question-papers", tags=["question-papers"])

DELETED = "Deleted"
_LIVE = or_(TeacherQuestionPaper.record_status.is_(None),
            TeacherQuestionPaper.record_status != DELETED)


def _chapter_names(db: Session, chapter_ids: list[int]) -> list[str]:
    """
    Chapter names for the ids given, in the order the teacher picked them.

    Ids that do not resolve are dropped rather than raising: RLS already
    confines this to the caller's school, so an id from elsewhere is simply
    not a chapter here. The caller decides what an empty result means.
    """
    rows = (
        db.query(ChapterMaster.chapter_id, ChapterMaster.chapter_name)
        .filter(ChapterMaster.chapter_id.in_(chapter_ids))
        .filter(or_(ChapterMaster.record_status.is_(None),
                    ChapterMaster.record_status != DELETED))
        .all()
    )
    by_id = {row.chapter_id: (row.chapter_name or "").strip() for row in rows}
    return [by_id[cid] for cid in chapter_ids if by_id.get(cid)]


# ── schemas ───────────────────────────────────────────────────────────────────

class BlueprintRow(BaseModel):
    """One section of the paper: how many questions of a type, and the marks each."""

    id: str
    count: int = 0
    each: float = 0


class QuestionPaperRequest(BaseModel):
    """
    What the Auto Test screen collects.

    chapterId is optional and kept only for callers that still send a single
    chapter. The screen sends chapterIds, and the generator now scopes a paper
    to every chapter it is given rather than the first one.

    Neither is required by the schema on purpose: an empty selection is a
    mistake the teacher can fix, and it should read as one rather than as the
    422 a required field produces before the handler ever runs.
    """
    chapterId: int | None = None
    chapterIds: list[int] = []
    difficulty: str = "Medium"
    totalMarks: int = 50
    questionType: str | None = None   # None = all question types
    # The Configure screen has always sent this and the schema never declared
    # it, so Pydantic dropped it on the way in and the paper's shape was lost
    # between the two. It is how many questions the teacher asked for.
    blueprint: list[BlueprintRow] = []

    def selected_chapter_ids(self) -> list[int]:
        ids = list(self.chapterIds) if self.chapterIds else []
        if self.chapterId is not None and self.chapterId not in ids:
            ids.insert(0, self.chapterId)
        return ids

    def question_count(self) -> int | None:
        """How many questions the blueprint asks for, or None if it is silent."""
        total = sum(row.count for row in self.blueprint if row.count > 0)
        return total or None


class CompetitivePaperRequest(BaseModel):
    """
    What the Configure screen collects for a competitive paper.

    Wider than QuestionPaperRequest and almost all of it optional, because the
    screen was built against the pattern the paper should follow while the
    generator still reads the older, narrower shape. Nothing here is required
    beyond the marks: a competitive paper may draw on the whole syllabus, so
    an empty chapter list is a valid answer, unlike a school test.
    """
    chapterId: Optional[int] = None
    chapterIds: list[int] = []
    difficulty: str = "Medium"
    totalMarks: int
    questionType: Optional[str] = None

    examType: Optional[str] = None
    examTarget: Optional[str] = None
    classLevel: Optional[str] = None
    subject: Optional[str] = None
    difficultyMix: Optional[dict[str, int]] = None
    blueprint: Optional[Any] = None
    minutes: Optional[int] = None
    negativeMarking: Optional[bool] = None
    questionCount: Optional[int] = None
    marksEach: Optional[int] = None


class QuestionPaperSave(BaseModel):
    title: str
    chapterId: Optional[int] = None
    subject: Optional[str] = None
    difficulty: Optional[str] = None
    totalMarks: Optional[int] = None
    questionType: Optional[str] = None
    # One of these must be present — whichever shape the AI produced.
    paperText: Optional[str] = None
    questions: Optional[list[Any]] = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title is required")
        return v[:255]


class QuestionPaperSummary(BaseModel):
    paper_id: int
    title: str
    subject: Optional[str] = None
    difficulty: Optional[str] = None
    total_marks: Optional[int] = None
    question_type: Optional[str] = None
    question_count: Optional[int] = None
    created_at: Optional[datetime] = None


class QuestionPaperOut(QuestionPaperSummary):
    chapter_id: Optional[int] = None
    paper_text: Optional[str] = None
    questions: Optional[list[Any]] = None


class QuestionPaperListResponse(BaseModel):
    papers: list[QuestionPaperSummary]
    total: int


def _summary(p: TeacherQuestionPaper) -> QuestionPaperSummary:
    return QuestionPaperSummary(
        paper_id=p.paper_id, title=p.title, subject=p.subject, difficulty=p.difficulty,
        total_marks=p.total_marks, question_type=p.question_type,
        question_count=len(p.questions) if isinstance(p.questions, list) else None,
        created_at=p.created_at,
    )


def _out(p: TeacherQuestionPaper) -> QuestionPaperOut:
    return QuestionPaperOut(**_summary(p).model_dump(), chapter_id=p.chapter_id,
                            paper_text=p.paper_text, questions=p.questions)


def _mine(db: Session, teacher_id: int, paper_id: int) -> TeacherQuestionPaper | None:
    return db.query(TeacherQuestionPaper).filter(
        TeacherQuestionPaper.paper_id == paper_id,
        TeacherQuestionPaper.teacher_id == teacher_id,
        _LIVE,
    ).first()


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate(
    body: QuestionPaperRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    The AI service scopes a paper to topic *names*, so the ids the screen
    sends are resolved here. Chapters are tenant-scoped by RLS, so an id
    belonging to another school simply does not resolve — which is the right
    answer, and says so plainly instead of generating from nothing.
    """
    chapter_ids = body.selected_chapter_ids()
    if not chapter_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Choose at least one chapter before generating a paper.",
        )

    topics = _chapter_names(db, chapter_ids)
    if not topics:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Those chapters are not in this school's syllabus. Pick them "
            "again from the list — a saved selection can outlive the chapter "
            "it pointed at.",
        )

    return await generate_question_paper(
        topics=topics,
        difficulty=body.difficulty,
        total_marks=body.totalMarks,
        question_type=body.questionType,
        num_questions=body.question_count(),
        teacher=teacher,
    )


@router.post("/generate-competitive")
async def generate_competitive(
    body: CompetitivePaperRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
):
    """
    A competitive paper, as opposed to a school test.

    Separate from /generate because the two collect different things: a
    school test is marked out of a fixed total and its blueprint has to reach
    it, while a competitive paper takes its total from the pattern and may
    ignore chapters entirely. Keeping them apart means /generate stays the
    narrow, required-chapter call it has always been.
    """
    return await generate_competitive_paper(body, teacher)


@router.post("", response_model=QuestionPaperOut, status_code=status.HTTP_201_CREATED)
def save_paper(
    body: QuestionPaperSave,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    text = (body.paperText or "").strip() or None
    questions = body.questions or None
    if not text and not questions:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to save — the paper is empty")

    paper = TeacherQuestionPaper(
        teacher_id=teacher.teacher_id,
        chapter_id=body.chapterId,
        title=body.title,
        subject=body.subject,
        difficulty=body.difficulty,
        total_marks=body.totalMarks,
        question_type=body.questionType,
        paper_text=text,
        questions=questions,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        record_status="Active",
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return _out(paper)


@router.get("", response_model=QuestionPaperListResponse)
def list_papers(
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    papers = (
        db.query(TeacherQuestionPaper)
        .filter(TeacherQuestionPaper.teacher_id == teacher.teacher_id, _LIVE)
        .order_by(TeacherQuestionPaper.created_at.desc().nullslast())
        .all()
    )
    return QuestionPaperListResponse(papers=[_summary(p) for p in papers], total=len(papers))


@router.get("/{paper_id}", response_model=QuestionPaperOut)
def get_paper(
    paper_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    paper = _mine(db, teacher.teacher_id, paper_id)
    if not paper:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question paper not found")
    return _out(paper)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(
    paper_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    paper = _mine(db, teacher.teacher_id, paper_id)
    if not paper:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question paper not found")
    paper.record_status = DELETED
    db.commit()
