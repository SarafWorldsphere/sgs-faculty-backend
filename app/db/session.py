import logging

from saraswati_tenant import apply_rls, bind_rls
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings
from app.db.pool import build_engine

log = logging.getLogger(__name__)

# Pool size is derived from the database's own max_connections at startup —
# see app/db/pool.py. Nothing here needs adjusting per environment.
engine = build_engine(
    settings.DATABASE_URL,
    service="sgs-faculty-api",
    slots=settings.DB_SERVICE_SLOTS,
    reserve=settings.DB_RESERVE,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
bind_rls(SessionLocal)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        # bind_rls reapplies the school on every later transaction. This call
        # is the strict check: a route reached with no school bound means the
        # middleware did not run, and that should fail here.
        apply_rls(db)
        yield db
    finally:
        # Closing rolls back, which talks to the server. On the AI endpoints the
        # session sits idle inside a transaction for as long as the upstream call
        # takes, and a connection dropped in that window makes the rollback raise
        # — turning a request that already succeeded into a 500. Cleanup is
        # best-effort; invalidate() discards the socket without touching it.
        try:
            db.close()
        except Exception:
            log.warning("DB session close failed; discarding connection", exc_info=True)
            try:
                db.invalidate()
            except Exception:
                pass
