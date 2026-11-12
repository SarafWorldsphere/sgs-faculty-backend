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

    AI_SERVICE_URL: str = "http://16.112.236.67:7007"

    # Printed on the lesson-plan masthead. Per-school, so it lives in .env.
    SCHOOL_NAME: str = ""

    # Which board the school follows. The AI writes to a different question
    # pattern for each, so every generation call carries it.
    #
    # Nothing in the database records this today — not on the school, the class
    # or the chapter — so until a school record holds it, it is one value per
    # deployment, exactly like SCHOOL_NAME above. A school runs one board.
    #
    # Typed as a Literal so a misspelling in .env fails at startup rather than
    # reaching the AI, which would quietly fall back to its own default and
    # produce the wrong pattern with nothing on screen to show it.
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
