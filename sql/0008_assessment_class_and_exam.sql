-- 0008: let an assessment say which class and which exam it belongs to.
--
-- Two gaps stop marks being entered and reported per class today:
--
--   1. sgs_assessments has class_name as free text and no class_id, so an
--      assessment cannot be reliably scoped to a class. Reports currently
--      count a teacher's assessments across every class they take.
--
--   2. There is no link to sgs_exam_master, so PT-1..PT-4 cannot be told
--      apart from each other or from a weekly class test.
--
-- Both are additive. Existing rows keep class_name and assessment_type, and
-- nothing that reads them today changes behaviour.
--
-- Deliberately NOT touching the assessment_type enum. It holds
-- quiz/test/exam/assignment, which does not match this school's PT/CT/Weekly
-- scheme, and Postgres cannot remove an enum value once added. exam_id carries
-- the real identity instead, and assessment_type stays as a broad category.
--
-- Run on STAGING first, production with the release.

ALTER TABLE sgs_assessments
    ADD COLUMN IF NOT EXISTS class_id BIGINT,
    ADD COLUMN IF NOT EXISTS exam_id  BIGINT;

CREATE INDEX IF NOT EXISTS ix_sgs_assessments_class_id
    ON sgs_assessments (class_id);
CREATE INDEX IF NOT EXISTS ix_sgs_assessments_exam_id
    ON sgs_assessments (exam_id);

-- Marks are entered and corrected by teachers, so the app needs to write and
-- update both tables. Results are deleted only when an assessment is removed.
GRANT SELECT, INSERT, UPDATE, DELETE ON sgs_assessments        TO swais_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON sgs_assessment_results TO swais_app_user;
GRANT USAGE, SELECT ON SEQUENCE sgs_assessments_assessment_id_seq   TO swais_app_user;
GRANT USAGE, SELECT ON SEQUENCE sgs_assessment_results_result_id_seq TO swais_app_user;
GRANT SELECT ON sgs_exam_master TO swais_app_user;
