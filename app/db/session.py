import logging

from saraswati_tenant import apply_rls
from saraswati_tenant.context import current_school
from sqlalchemy import event
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


class Base(DeclarativeBase):
    pass


@event.listens_for(SessionLocal, "after_begin")
def _bind_school_to_transaction(session, transaction, connection):
    """Re-apply the school every time a transaction begins.

    `set_config('app.tenant_id', ..., true)` is deliberately transaction-local:
    it cannot leak to the next request that borrows the same pooled connection.
    The cost is that it dies with the transaction that set it.

    Setting it once in get_db() is enough for a read-only module, but this API
    commits nineteen times across its services and rolls back twice in deps.py
    to keep AI requests out of an open transaction. Every one of those ends the
    transaction, and the next query would then run with no school bound — which
    the policy reads as "no rows", not as an error. Marks would save and then
    read back empty.

    Binding it to `after_begin` means every transaction on this session carries
    the school, however many there are, with nothing for a service to remember.

    Nothing is bound outside a request — startup probes, Alembic and scripts —
    and those must still work, so an unbound context is not an error here. The
    policy is the thing that keeps those sessions honest: no school bound means
    no school rows, by design.
    """
    try:
        school = current_school()
    except RuntimeError:
        return

    connection.exec_driver_sql(
        "SELECT set_config('app.tenant_id', %s, true)", (school.tenant_id,)
    )


def get_db():
    db = SessionLocal()
    try:
        # The listener above covers every transaction this session opens. This
        # call is what the other modules write, and it makes the binding visible
        # where a reader expects to find it. It is also deliberately strict:
        # reaching a route with no school bound means the middleware did not
        # run, and that should fail loudly here rather than quietly return
        # nothing from every query.
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
