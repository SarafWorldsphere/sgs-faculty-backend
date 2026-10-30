from datetime import date, datetime
from pydantic import BaseModel, field_validator

from app.core.dates import reject_past


class AssignmentOut(BaseModel):
    assignment_id: int
    title: str | None = None
    subject: str | None = None
    chapter_id: int | None = None
    chapter_name: str | None = None
    due_date: date | None = None
    submitted_count: int = 0
    # Number of students this assignment was given to — the result rows, not
    # the class size. A targeted assignment reports its target count.
    total_students: int = 0


class AssignmentStudentRow(BaseModel):
    student_id: int
    full_name: str | None = None
    roll_no: str | None = None
    status: str | None = None
    submitted_at: datetime | None = None
    # What they turned in. The file itself is fetched separately — this only
    # says whether one exists and what it is.
    submission_text: str | None = None
    submission_link: str | None = None
    submitted_file_name: str | None = None
    submitted_file_size: int | None = None
    marks_obtained: float | None = None
    total_marks: float | None = None


class AssignmentStudentsResponse(BaseModel):
    assignment_id: int
    title: str | None = None
    students: list[AssignmentStudentRow]
    total: int
    submitted_count: int = 0


class AssignmentListResponse(BaseModel):
    assignments: list[AssignmentOut]
    total: int


class AssignmentCreate(BaseModel):
    title: str
    text: str | None = None
    subject_id: int | None = None
    chapter_id: int | None = None
    due_date: date | None = None
    # Who gets it. Omitted or empty = every student on the teacher's roll.
    # Each id is checked against the roll at create time.
    student_ids: list[int] | None = None

    # The date picker also blocks past dates; this is the check that holds
    # when the request doesn't come from the picker.
    @field_validator("due_date")
    @classmethod
    def _due_not_past(cls, v):
        return reject_past(v, "Due date")

    @field_validator("student_ids")
    @classmethod
    def _dedupe(cls, v):
        return sorted(set(v)) if v else v
