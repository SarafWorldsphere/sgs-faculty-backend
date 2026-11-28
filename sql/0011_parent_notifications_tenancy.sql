-- 0011: make parent_notifications writable.
--
-- Sending a message to a parent from the Students screen returns HTTP 500.
-- The application code is fine; the table was created outside the pattern
-- every other tenant-scoped table in this schema follows, and two separate
-- faults each independently prevent an insert.
--
-- 1. No stamp_tenant trigger.
--
--    tenant_id is NOT NULL with no default, and no caller sets it — the
--    model does not map the column, exactly as notice_board's does not,
--    because notice_board carries a BEFORE INSERT trigger that fills it from
--    the request's school. parent_notifications has no such trigger, so every
--    insert fails the NOT NULL constraint. That is the 500.
--
-- 2. The row-level security policy reads a setting name nothing sets.
--
--    It tests current_setting('app.current_tenant_id'), while the tenant kit
--    sets app.tenant_id and every other policy in the database goes through
--    platform.current_tenant_id(), which reads that. So the policy always
--    compares against NULL: reads return nothing and writes are refused.
--    parent_notifications is the only table in the schema with this spelling
--    — verified against pg_policy — so this is a one-off slip, not a
--    convention to preserve.
--
-- The table is empty, so there is nothing to backfill and no risk of
-- orphaning rows under the corrected policy.
--
-- Must run as the table owner (swaispostgres); saas_app cannot alter it.
-- Safe to run more than once.
--
--   psql "$DATABASE_URL" -f sql/0011_parent_notifications_tenancy.sql

BEGIN;

-- 1. Fill tenant_id from the request's school, as notice_board does.
DROP TRIGGER IF EXISTS stamp_tenant ON parent_notifications;
CREATE TRIGGER stamp_tenant
    BEFORE INSERT OR UPDATE ON parent_notifications
    FOR EACH ROW EXECUTE FUNCTION platform.stamp_tenant_id();

-- 2. Use the same isolation expression as every other table, and state
--    WITH CHECK explicitly so inserts are judged by it rather than by an
--    implied copy of USING.
ALTER TABLE parent_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE parent_notifications FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON parent_notifications;
CREATE POLICY tenant_isolation ON parent_notifications
    USING      (tenant_id = (SELECT platform.current_tenant_id()))
    WITH CHECK (tenant_id = (SELECT platform.current_tenant_id()));

COMMIT;

-- After running, this should insert and then read back one row:
--
--   SET app.tenant_id = '<a real tenant uuid>';
--   INSERT INTO parent_notifications
--       (teacher_id, student_id, notification_type, message_text, sent_via)
--   VALUES (<teacher>, <student>, 'general', 'test', 'manual');
--   SELECT count(*) FROM parent_notifications;   -- expect 1
