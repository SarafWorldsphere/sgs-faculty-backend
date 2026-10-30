"""
UserMaster — authentication table.
Maps to users_masters table.
"""

from sqlalchemy import Column, BigInteger, Integer, String, Boolean, DateTime, Text

from app.db.session import Base


class UserMaster(Base):
    __tablename__ = "users_masters"

    user_id         = Column(BigInteger, primary_key=True)
    login_id        = Column(String(255), unique=True, nullable=False, index=True)
    password_hash   = Column(Text, nullable=False)
    full_name       = Column(String(255), nullable=True)
    email_id        = Column(String(255), nullable=True, index=True)
    mobile_no       = Column(String(50), nullable=True)
    role_id         = Column(BigInteger, nullable=True)
    # school_id is gone: the kit replaced it with tenant_id, which the stamp
    # trigger fills and the policy filters. Declaring it here made every query
    # on this table ask for a column the database does not have.
    is_active       = Column(Boolean, default=True, nullable=True)
    created_datetime = Column(DateTime, nullable=True)
    record_status   = Column(String(50), nullable=True)
    version_no      = Column(Integer, nullable=True)
