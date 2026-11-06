"""
NoticeBoard — maps to notice_board table (school announcements).
Faculty view is read-only.
"""

from sqlalchemy import Column, BigInteger, String, Text, Date

from app.db.session import Base


class NoticeBoard(Base):
    __tablename__ = "notice_board"

    notice_id        = Column(BigInteger, primary_key=True)
    notice_title     = Column(String, nullable=True)
    notice_text      = Column(Text, nullable=True)
    notice_date      = Column(Date, nullable=True)
    applicable_class = Column(String, nullable=True)
    posted_by        = Column(BigInteger, nullable=True)
    # Soft-delete marker. The admin dashboard deletes a notice by setting this,
    # so anything reading notices must filter on it or deleted announcements
    # keep appearing on the faculty dashboard.
    record_status    = Column(String, nullable=True)
