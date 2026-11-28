"""
ChapterMaster — maps chapter_master.

The canonical chapter record. Linked to a subject via subject_id (class is
derived through the subject). chapter_content.chapter_id and
file_storage_metadata.entity_id both reference chapter_id here.
"""

from sqlalchemy import BigInteger, Column, Integer, String, Text

from app.db.session import Base


class ChapterMaster(Base):
    __tablename__ = "chapter_master"

    chapter_id          = Column(BigInteger, primary_key=True, autoincrement=True)
    subject_id          = Column(BigInteger, nullable=True, index=True)
    chapter_no          = Column(Integer,    nullable=True)
    chapter_name        = Column(String,     nullable=True)
    chapter_description = Column(Text,       nullable=True)
    chapter_order       = Column(Integer,    nullable=True)
    record_status       = Column(String,     nullable=True)
    version_no          = Column(Integer,    nullable=True)
    book_volume_number  = Column(String,     nullable=False, default="1")
