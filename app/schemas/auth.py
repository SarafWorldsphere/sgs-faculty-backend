from pydantic import BaseModel, EmailStr, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SSOTokenRequest(BaseModel):
    """
    One of email or phone. The login portal sends whichever the teacher used —
    Google SSO gives an email, OTP login gives a phone. This used to require
    email, so every OTP login was rejected with a 422 before the endpoint ran,
    and the portal quietly redirected to the dashboard with no token.
    """

    email: EmailStr | None = None
    phone: str | None = None

    @model_validator(mode="after")
    def _needs_one_identifier(self):
        if not self.email and not self.phone:
            raise ValueError("Either email or phone is required")
        return self


class ClassOption(BaseModel):
    """
    One class a teacher may work in — what the faculty class selector renders.

    `class_assigned` and `section` below still describe the *primary*
    assignment, so a client that ignores this list behaves exactly as before.
    """

    class_id: int
    class_name: str | None = None
    sections: list[str] = []
    subjects: list[str] = []
    is_primary: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    teacher_id: str
    name: str
    email: str
    subject: str | None = None
    class_assigned: str | None = None
    section: str | None = None
    avatar_initials: str | None = None
    school_name: str | None = None
    total_students: int | None = None
    classes: list[ClassOption] = []


class MeResponse(BaseModel):
    teacher_id: str
    name: str
    email: str
    subject: str | None = None
    class_assigned: str | None = None
    section: str | None = None
    avatar_initials: str | None = None
    school_name: str | None = None
    total_students: int | None = None
    classes: list[ClassOption] = []
