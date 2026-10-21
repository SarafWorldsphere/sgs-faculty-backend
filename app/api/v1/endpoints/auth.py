from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_active_class_id, get_current_teacher
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.teacher import TeacherMaster
from app.models.user import UserMaster
from app.schemas.auth import LoginRequest, MeResponse, SSOTokenRequest, TokenResponse
from app.services import teacher_class_service
from app.services.auth_service import authenticate_teacher, get_class_context

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Teacher login.
    Returns JWT (1-day expiry) + teacher profile info.
    """
    try:
        return authenticate_teacher(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


@router.get("/me", response_model=MeResponse)
def me(
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """
    Returns the current teacher's profile from a valid JWT.
    Used by the faculty app on load to restore session from token.

    `class_id` makes the class name and headcount follow the class the teacher
    has selected. Omitted — as on first load — it reports their primary class.
    """
    class_display, total_students = get_class_context(db, teacher, class_id)
    options = teacher_class_service.class_options(db, teacher)
    selected = next((o for o in options if o.class_id == class_id), None)

    return MeResponse(
        teacher_id=teacher.teacher_id,
        name=teacher.full_name,
        email=teacher.email_id,
        subject=teacher.subject_name,
        class_assigned=class_display,
        section=", ".join(selected.sections) if selected and selected.sections else teacher.section_1,
        avatar_initials=(teacher.full_name or "")[:2].upper() or None,
        school_name=None,
        total_students=total_students,
        classes=options,
    )


@router.post("/sso-token", response_model=TokenResponse)
def sso_token(
    payload: SSOTokenRequest,
    x_sso_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Internal SSO endpoint — called by the login portal once it has verified the
    teacher, either through Google (email) or an SMS OTP (phone). Exchanges that
    verified identifier for a JWT without requiring a password. Protected by a
    shared secret header (X-SSO-Secret).
    """
    if not settings.SSO_SECRET or x_sso_secret != settings.SSO_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid SSO secret")

    roll = db.query(TeacherMaster).filter(TeacherMaster.is_active == True)

    if payload.email:
        email = payload.email.lower()
        teacher = roll.filter(TeacherMaster.email_id == email).first()
    else:
        # phone is a bigint column holding ten bare digits — no country code,
        # no separators. Strip whatever the portal sends down to the last ten.
        digits = "".join(ch for ch in (payload.phone or "") if ch.isdigit())[-10:]
        if len(digits) != 10:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Phone must contain ten digits")
        teacher = roll.filter(TeacherMaster.phone == int(digits)).first()

    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    # The response echoes the teacher's own email, which is the one the
    # dashboard shows — not necessarily the identifier used to log in.
    email = (teacher.email_id or "").lower()

    user = db.query(UserMaster).filter(UserMaster.login_id == email).first()
    user_id = user.user_id if user else teacher.teacher_id

    token = create_access_token(data={
        "sub": str(user_id),
        "teacher_id": teacher.teacher_id,
        "role": "teacher",
    })

    return TokenResponse(
        access_token=token,
        teacher_id=teacher.teacher_id,
        name=teacher.full_name,
        email=email,
        subject=teacher.subject_name,
        class_assigned=str(teacher.class_id) if teacher.class_id else None,
        section=teacher.section_1,
        avatar_initials=(teacher.full_name or "")[:2].upper() or None,
        school_name=None,
        classes=teacher_class_service.class_options(db, teacher),
    )


@router.post("/logout")
def logout():
    """
    Client-side logout — just tell the client to drop the token.
    (Stateless JWT, no server-side invalidation needed for now.)
    """
    return {"message": "Logged out successfully"}
