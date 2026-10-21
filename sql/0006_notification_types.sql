-- 0006: allow the notification types the Faculty app actually offers.
--
-- sgs_parent_notifications.notification_type is the enum `notification_type`,
-- whose values were let_drop / peer_help / good_manners / table_manners /
-- general — written for behaviour notes. The Faculty "Notify Parent" modal
-- offers Performance / Homework / Attendance / General, so three of its four
-- options cannot be stored. This adds them.
--
-- ADD VALUE is additive and safe; existing rows and values are untouched.
-- Postgres cannot remove an enum value, so this is effectively one-way.
-- Run on STAGING first, production with the release.

ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'performance';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'homework';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'attendance';

-- The app writes as swais_app_user.
GRANT SELECT, INSERT, UPDATE ON sgs_parent_notifications TO swais_app_user;
GRANT USAGE, SELECT ON SEQUENCE sgs_parent_notifications_notification_id_seq TO swais_app_user;
