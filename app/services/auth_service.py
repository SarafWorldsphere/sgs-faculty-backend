from sqlalchemy.orm import Session

from app.models.user import UserMaster
from app.models.teacher import TeacherMaster
from app.models.class_master import ClassMaster
from app.models.student import StudentMaster
from app.core.security import verify_password, create_access_token
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import student_service, teacher_class_service

# Kept as a module-level name: the ordinal formatting now lives with the rest of
# the class resolution in teacher_class_service.
_class_display = teacher_class_service.class_display_name


def get_class_context(
    db: Session, teacher: TeacherMaster, class_id=None
) -> tuple[str | None, int]:
    """
    Resolve a display class name (from sgs_class_master) and the count of active
    students in it. Used by both /login and /me so the header/dashboard always
    show real values.

    `class_id` defaults to the teacher's primary assignment — the behaviour
    before a teacher could have more than one class.
    """
    class_id = class_id or teacher.class_id
    if not class_id:
        return None, 0

    cls = db.query(ClassMaster).filter(ClassMaster.class_id == class_id).first()
    class_name = (cls.class_name if cls and cls.class_name else _class_display(class_id))

    # Same filter as the Students tab — see student_service.
    total_students = student_service.roll_count(db, class_id)
    return class_name, total_students


def authenticate_teacher(db: Session, payload: LoginRequest) -> TokenResponse:
    # 1. Find user by login_id (email is used as login_id in sgs_users_masters)
    user = db.query(UserMaster).filter(
        UserMaster.login_id == payload.email,
        UserMaster.is_active == True,
    ).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise ValueError("Invalid email or password")

    # 2. Get teacher profile — linked by matching email_id (no FK in sgs schema)
    teacher = db.query(TeacherMaster).filter(
        TeacherMaster.email_id == user.login_id,
    ).first()
    if not teacher:
        raise ValueError("No teacher profile found for this account")

    # 3. Issue JWT
    token = create_access_token(
        data={
            "sub": str(user.user_id),
            "teacher_id": teacher.teacher_id,
            "role": "teacher",
        }
    )

    # Resolve human-readable class name + live student count from master tables
    class_display, total_students = get_class_context(db, teacher)

    return TokenResponse(
        access_token=token,
        teacher_id=teacher.teacher_id,
        name=teacher.full_name,
        email=user.login_id,
        subject=teacher.subject_name,
        class_assigned=class_display,
        section=teacher.section_1,
        avatar_initials=None,
        school_name=None,
        total_students=total_students,
        # Every class this teacher takes. One entry for a single-class teacher,
        # so the frontend has no special case.
        classes=teacher_class_service.class_options(db, teacher),
    )
