import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher
from app.db.session import get_db
from app.models.lesson_plan import TeacherLessonPlan
from app.models.teacher import TeacherMaster
from app.schemas.lesson_plan import (
    LessonPlanGenerateRequest,
    LessonPlanSaveRequest,
    LessonPlanCompletionRequest,
    LessonPlanListResponse,
    LessonPlanOut,
)
from app.services.ai_service import generate_lesson_plan

router = APIRouter(prefix="/lesson-plans", tags=["lesson-plans"])


@router.post("/generate")
async def generate(
    body: LessonPlanGenerateRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Call the AI service and return a structured lesson plan."""
    if not body.chapter:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="topic is required",
        )
    # db is for the header's class name only — class_id alone printed as
    # "Class 32 A", the row number rather than the class.
    return await generate_lesson_plan(body, teacher, db)


@router.get("", response_model=LessonPlanListResponse)
def list_plans(
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    records = (
        db.query(TeacherLessonPlan)
        .filter(TeacherLessonPlan.teacher_id == teacher.teacher_id)
        .order_by(TeacherLessonPlan.created_at.desc())
        .all()
    )

    plans: list[LessonPlanOut] = []
    for record in records:
        # plan_data holds the full structured plan as a JSON string.
        try:
            full = json.loads(record.plan_data) if record.plan_data else {}
        except (ValueError, TypeError):
            full = {}
        # Backfill summary fields so the viewer always has them, even for
        # legacy rows saved before a field existed.
        full.setdefault("title", record.title)
        full.setdefault("chapter_text", record.chapter_text)
        full.setdefault("duration_minutes", record.duration_minutes)

        plans.append(LessonPlanOut(
            lesson_plan_id=record.lesson_plan_id,
            title=record.title,
            chapter_text=record.chapter_text,
            duration_minutes=record.duration_minutes,
            created_at=record.created_at,
            plan=full,
        ))

    return LessonPlanListResponse(plans=plans)


@router.post("", status_code=status.HTTP_201_CREATED)
def save_plan(
    body: LessonPlanSaveRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    plan = body.plan
    record = TeacherLessonPlan(
        teacher_id=teacher.teacher_id,
        title=plan.get("title", "Untitled Plan"),
        chapter_text=plan.get("chapter_text"),
        duration_minutes=plan.get("duration_minutes"),
        plan_data=json.dumps(plan),
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"lesson_plan_id": record.lesson_plan_id, "message": "Plan saved"}


@router.patch("/{plan_id}/completion")
def record_completion(
    plan_id: int,
    body: LessonPlanCompletionRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Stamp the actual date of completion on a saved plan.

    Separate from generation because the teacher only knows this date after
    the lesson has been taught — at generation time the field is blank on the
    paper form too.
    """
    record = db.query(TeacherLessonPlan).filter(
        TeacherLessonPlan.lesson_plan_id == plan_id,
        TeacherLessonPlan.teacher_id == teacher.teacher_id,
    ).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    try:
        plan = json.loads(record.plan_data) if record.plan_data else {}
    except (ValueError, TypeError):
        plan = {}
    plan.setdefault("header", {})["actual_completion"] = body.actualCompletion.isoformat()

    record.plan_data = json.dumps(plan)
    db.commit()
    return {"lesson_plan_id": plan_id, "actual_completion": body.actualCompletion.isoformat()}


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    record = db.query(TeacherLessonPlan).filter(
        TeacherLessonPlan.lesson_plan_id == plan_id,
        TeacherLessonPlan.teacher_id == teacher.teacher_id,
    ).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    db.delete(record)
    db.commit()
