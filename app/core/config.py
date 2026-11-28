from pydantic_settings import BaseSettings
from typing import List, Literal


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 1 day

    SSO_SECRET: str = ""  # Shared secret for staging → backend SSO token requests

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    CORS_ORIGINS: str = "http://localhost:3000"

    # The SSS Faculty AI service. It serves /api/faculty/* on port 7000; the
    # old service at 16.112.236.67:7007 served /api/v1/ai/teacher/* and is
    # gone. Both the port and the path prefix changed, so an old value here
    # fails as a refused connection rather than a 404.
    AI_SERVICE_URL: str = "http://localhost:7000"

    # Sent as `client_name` on every AI call; the service logs token usage
    # against it. A tenant overrides it with an `aiClientName` key in its
    # config — see _client_name() in app/services/ai_service.py.
    AI_CLIENT_NAME: str = "SSS"

    # SCHOOL_NAME was here. The masthead now reads the school this request
    # resolved to (current_school().config), because one process serves every
    # school and a single configured name would be wrong for all but one.

    # Host lookup for SchoolMiddleware. Points at the control database, which
    # on the shared setup is the same database as DATABASE_URL.
    SARASWATI_DATABASE_URL: str = ""

    # Fallback board, used only when no school resolved for the request.
    #
    # The board now lives on the school itself, in the tenant config, and
    # ai_service reads it from there — one process serves every school, and
    # the schools on it do not share a board, so a single configured value
    # would be wrong for one of them on every paper it generated.
    #
    # This stays for the single-school case and for a tenant whose config
    # predates the key. Typed as a Literal so a misspelling in .env fails at
    # startup rather than reaching the AI, which would quietly fall back to
    # its own default and produce the wrong pattern with nothing on screen
    # to show it.
    SCHOOL_BOARD: Literal["State", "CBSE"] = "State"

    # One period, in minutes — the form counts periods, the AI counts minutes.
    PERIOD_MINUTES: int = 45

    # Connection-pool budget. SLOTS counts *workers* sharing this database
    # instance, not services — four uvicorn workers across six APIs is 24.
    # RESERVE is held back for migrations, pgAdmin and the superuser reserve.
    DB_SERVICE_SLOTS: int = 12
    DB_RESERVE: float = 0.2

    # S3 — study material PDFs
    AWS_REGION: str            = "ap-south-2"
    AWS_S3_BUCKET_NAME: str    = ""
    AWS_ACCESS_KEY_ID: str     = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
