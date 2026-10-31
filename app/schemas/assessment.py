from datetime import date
from typing import Optional, List
from pydantic import BaseModel, field_validator, model_validator
from app.models.assessment import AssessmentType


class ExamOut(BaseModel):
    """A scheduled school exam — PT-1..PT-4 and the summatives."""
    exam_id:    int
    exam_name:  Optional[str] = None
    exam_type:  Optional[str] = None
    start_date: Optional[date] = None
    end_date:   Optional[date] = None

    model_config = {"from_attributes": True}


class ExamListResponse(BaseModel):
    exams: List[ExamOut]


class StudentMarkIn(BaseModel):
    """One student's mark on one test."""
    student_id:     int
    marks_obtained: Optional[float] = None
    is_absent:      bool = False

    @model_validator(mode="after")
    def _absent_or_marked(self):
        # An absent student has no mark. Allowing both invites a row that says
        # the child scored 12 and did not sit the test.
        if self.is_absent and self.marks_obtained is not None:
            raise ValueError("An absent student cannot have marks")
        return self


class MarksEntryRequest(BaseModel):
    """Create a test and record its marks in one call.

    Deliberately one call rather than create-then-fill: a test row with no
    results is useless, and two calls means a half-saved test whenever the
    second one fails.
    """
    title:           str
    subject:         Optional[str] = None
    assessment_date: date
    max_marks:       float
    # Points at sgs_exam_master for PT-1..PT-4. Leave out for a weekly class
    # test, which is not a scheduled school exam.
    exam_id:         Optional[int] = None
    assessment_type: AssessmentType = AssessmentType.test
    marks:           List[StudentMarkIn]

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Title is required")
        return v

    @field_validator("max_marks")
    @classmethod
    def _max_marks(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Maximum marks must be greater than zero")
        return v

    @model_validator(mode="after")
    def _marks_within_range(self):
        if not self.marks:
            raise ValueError("At least one student's marks are required")

        over = [m.student_id for m in self.marks
                if m.marks_obtained is not None and m.marks_obtained > self.max_marks]
        if over:
            raise ValueError(f"Marks above the maximum of {self.max_marks} for students: {over}")

        negative = [m.student_id for m in self.marks
                    if m.marks_obtained is not None and m.marks_obtained < 0]
        if negative:
            raise ValueError(f"Negative marks for students: {negative}")

        seen = [m.student_id for m in self.marks]
        if len(seen) != len(set(seen)):
            raise ValueError("The same student appears more than once")
        return self


class MarksUpdateRequest(BaseModel):
    """Correct the marks on a test that has already been saved."""
    marks: List[StudentMarkIn]

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.marks:
            raise ValueError("At least one student's marks are required")
        return self


class ResultOut(BaseModel):
    result_id:      int
    student_id:     int
    student_name:   str
    roll_number:    str
    marks_obtained: Optional[float]
    max_marks:      float
    percentage:     Optional[float]
    is_absent:      bool = False

    model_config = {"from_attributes": True}


class AssessmentOut(BaseModel):
    assessment_id:   int
    title:           str
    subject:         Optional[str]
    chapter:         Optional[str]
    assessment_type: AssessmentType
    max_marks:       float
    assessment_date: Optional[date]
    total_students:  int
    submitted:       int
    class_average:   Optional[float]
    class_id:        Optional[int] = None
    exam_id:         Optional[int] = None
    exam_name:       Optional[str] = None
    absent_count:    int = 0

    model_config = {"from_attributes": True}


class AssessmentDetailOut(AssessmentOut):
    results: List[ResultOut]


class AssessmentListResponse(BaseModel):
    assessments: List[AssessmentOut]
    total:       int
