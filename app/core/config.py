from pydantic_settings import BaseSettings
from typing import List


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

    AI_SERVICE_URL: str = "http://16.112.236.67:7007"

    # SCHOOL_NAME was here. The masthead now reads the school this request
    # resolved to (current_school().config), because one process serves every
    # school and a single configured name would be wrong for all but one.

    # Host lookup for SchoolMiddleware. Points at the control database, which
    # on the shared setup is the same database as DATABASE_URL.
    SARASWATI_DATABASE_URL: str = ""

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
