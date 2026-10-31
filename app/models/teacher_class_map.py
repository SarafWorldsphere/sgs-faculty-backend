"""
TeacherClassMap — every class/section/subject a teacher is assigned to.

sgs_teacher_master carries one class_id and two section columns, which is all a
class teacher needs. Teachers who take several *classes* do not fit there:
teacher_id is the primary key and fourteen tables reference it, so a second row
per teacher is not an option.

This table is purely additive. The columns on sgs_teacher_master keep their
meaning — they are the teacher's primary assignment, and everything that read
them before still reads them. A teacher with no rows here behaves exactly as
before, which is why this can ship without touching existing data.

teacher_id is varchar to match sgs_teacher_master.teacher_id ('T02', 'H01') and
every sibling table. No foreign key: the production tables are owned by a
different role, and the map is written by data entry before the teacher row is
always present.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String

from app.db.session import Base

DELETED = "Deleted"


class TeacherClassMap(Base):
    __tablename__ = "sgs_teacher_class_map"

    map_id           = Column(BigInteger, primary_key=True)
    teacher_id       = Column(String(50),  nullable=False, index=True)
    class_id         = Column(BigInteger,  nullable=False)
    section          = Column(String(10),  nullable=False)
    subject_name     = Column(String(150), nullable=True)
    is_class_teacher = Column(Boolean,     nullable=True, default=False)
    record_status    = Column(String(20),  nullable=True, default="Active")
    created_at       = Column(DateTime,    nullable=True)
