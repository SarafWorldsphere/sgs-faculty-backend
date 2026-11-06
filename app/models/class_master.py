"""
ClassMaster — maps to class_master table.
Holds the human-readable class name (e.g. "8th Grade") + section for a class_id.
"""

from sqlalchemy import Column, BigInteger, String

from app.db.session import Base


class ClassMaster(Base):
    __tablename__ = "class_master"

    class_id     = Column(BigInteger, primary_key=True)
    class_name   = Column(String(100), nullable=True)
    section_name = Column(String(50),  nullable=True)
