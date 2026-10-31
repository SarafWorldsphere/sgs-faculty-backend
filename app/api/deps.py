"""
Shared FastAPI dependencies.

get_current_teacher — verifies JWT and returns the authenticated teacher's ID.
get_active_class_id  — resolves which class the request is about, and checks the
                       teacher is actually assigned to it.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.core.security import decode_token
from app.models.teacher import TeacherMaster
from app.models.user import UserMaster
from app.services import teacher_class_service

bearer_scheme = HTTPBearer()

_DEV_TEACHER = TeacherMaster(
    teacher_id=1,
    full_name="Dev Teacher",
    email_id="dev@swais.edu",
    subject_name="Social Studies",
    class_id=8,
    section_1="A",
    is_active=True,
)


def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> TeacherMaster:
    token = credentials.credentials

    if settings.APP_ENV == "development" and token == "dev":
        return _DEV_TEACHER

    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    teacher_id: int = payload.get("teacher_id")
    if not teacher_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing teacher_id")

    teacher = db.query(TeacherMaster).filter(TeacherMaster.teacher_id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    # This query opens a transaction that would otherwise stay open for the whole
    # request. The AI endpoints then wait up to 60s on the upstream service, and
    # the database kills any session idle *inside a transaction* for 30s
    # (idle_in_transaction_session_timeout) — which made the session teardown
    # raise and turned completed requests into 500s.
    #
    # Detaching the teacher first, then ending the transaction, leaves the session
    # merely idle. idle_session_timeout is 0, so that is never killed, and the next
    # query on this session starts a fresh transaction on its own.
    db.expunge(teacher)
    db.rollback()

    return teacher


def get_active_class_id(
    class_id: Optional[int] = Query(
        default=None,
        description="Which of the teacher's classes this request is about. "
                    "Omitted means their primary class, as before.",
    ),
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
) -> Optional[int]:
    """
    The class a class-scoped endpoint should work on.

    No class_id means the teacher's primary assignment — the behaviour every
    endpoint had before multiple classes existed, so old clients are unaffected.

    A class_id the teacher is not assigned to is refused. This is the whole
    authorisation check for the feature: the parameter comes from the client, so
    without it a teacher could read any class in the school by editing a URL.
    """
    if class_id is None:
        return teacher.class_id

    allowed = teacher_class_service.allowed_class_ids(db, teacher)
    # Same reason as above: leave the session idle rather than idle-in-transaction,
    # so a slow AI call downstream cannot have its session killed at teardown.
    db.rollback()

    if class_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this class",
        )
    return class_id
