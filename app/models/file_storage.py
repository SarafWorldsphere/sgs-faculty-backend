"""
FileStorageMetadata — maps file_storage_metadata.

Generic file table keyed by (entity_type, entity_id). Chapter study material
uses entity_type='CHAPTER_STUDY_MATERIAL' with entity_id = chapter_id.
file_url holds an s3://bucket/key URI.
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from app.db.session import Base

ENTITY_CHAPTER_STUDY_MATERIAL = "CHAPTER_STUDY_MATERIAL"
ENTITY_ASSIGNMENT_ATTACHMENT = "ASSIGNMENT_ATTACHMENT"


class FileStorageMetadata(Base):
    __tablename__ = "file_storage_metadata"

    file_id             = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_type         = Column(String,   nullable=False)
    entity_id           = Column(BigInteger, nullable=False, index=True)
    file_name           = Column(String,   nullable=False)
    file_url            = Column(Text,     nullable=False)
    uploaded_by         = Column(BigInteger, nullable=True)
    created_at          = Column(DateTime, nullable=True)
    created_user_id     = Column(String,   nullable=True)
    created_ip_address  = Column(String,   nullable=True)
    modified_datetime   = Column(DateTime, nullable=True)
    modified_user_id    = Column(String,   nullable=True)
    modified_ip_address = Column(String,   nullable=True)
    record_status       = Column(String,   nullable=True)
    version_no          = Column(Integer,  nullable=True)
    updated_at          = Column(DateTime, nullable=True)
