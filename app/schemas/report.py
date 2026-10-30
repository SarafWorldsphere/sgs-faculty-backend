from typing import Optional, List
from pydantic import BaseModel


class StudentReportRow(BaseModel):
    student_id:       int
    name:             str
    roll_number:      str
    total_assessed:   int          # number of assessments they sat
    average_marks:    Optional[float]
    average_percent:  Optional[float]
    highest_marks:    Optional[float]
    lowest_marks:     Optional[float]
    rank:             int


class ReportResponse(BaseModel):
    teacher_id:    int
    class_name:    str
    section:       str
    total_students: int
    total_assessments: int
    students: List[StudentReportRow]
