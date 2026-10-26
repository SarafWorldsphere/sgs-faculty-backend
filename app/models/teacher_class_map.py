"""
TeacherClassMap — every class/section/subject a teacher is assigned to.

Maps to the kit's `teacher_class_subject_map`. There is no module-specific
table: the kit is the single schema, and a second table describing which
teacher takes which class is the kind of thing that is fine for a month and
then nobody knows which one is authoritative.

teacher_master carries one class_id and two section columns, which is all a
class teacher needs. Teachers who take several *classes* do not fit there:
teacher_id is the primary key and fourteen tables reference it, so a second
row per teacher is not an option. This table holds the full set.

It stays purely additive. The columns on teacher_master keep their meaning —
they are the teacher's primary assignment, and everything that read them
before still reads them. A teacher with no rows here behaves exactly as
before.

tenant_id is deliberately not declared. The kit's stamp trigger fills it on
insert and the row-level security policy filters it on read, so a model that
names it would be claiming ownership of a column the database manages.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String

from app.db.session import Base


class TeacherClassMap(Base):
    __tablename__ = "teacher_class_subject_map"

    assignment_id    = Column(BigInteger, primary_key=True)
    teacher_id       = Column(BigInteger,  nullable=False, index=True)
    class_id         = Column(BigInteger,  nullable=False)
    section          = Column(String(50),  nullable=True)
    subject_name     = Column(String(255), nullable=False)
    # NOT NULL in the kit. Rows written by faculty must set it; the migration
    # fills existing rows from the current academic year.
    academic_year    = Column(String(50),  nullable=False)
    is_class_teacher = Column(Boolean,     nullable=False, default=False)
    # Replaces the old record_status text column. A live row is is_active true.
    is_active        = Column(Boolean,     nullable=False, default=True)
    created_at       = Column(DateTime,    nullable=True)
    updated_at       = Column(DateTime,    nullable=True)
