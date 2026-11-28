from sqlalchemy import BigInteger, Boolean, Column, Integer, Text, DateTime
from sqlalchemy import String
from app.db.session import Base


class SgsChapterContent(Base):
    __tablename__ = "chapter_content"

    chapter_content_id = Column(BigInteger, primary_key=True, autoincrement=True)
    chapter_id         = Column(BigInteger, nullable=True)
    content_title      = Column(String, nullable=True)
    chapter_name       = Column(String, nullable=True)
    full_text_content  = Column(Text, nullable=True)
    is_active          = Column(Boolean, default=True)
    record_status      = Column(String, nullable=True)
    version_no         = Column(Integer, nullable=True)
    created_datetime   = Column(DateTime, nullable=True)
