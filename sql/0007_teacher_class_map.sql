-- 0007: sgs_teacher_class_map — a teacher's full class/section/subject list.
--
-- sgs_teacher_master holds one class_id and two section columns. A teacher who
-- takes several classes does not fit: teacher_id is the primary key there and
-- fourteen tables reference it, so a second row per teacher is not an option.
--
-- Purely additive. No existing column is changed, renamed or removed. The 42
-- places that read section_1/section_2 keep working unchanged, and a teacher
-- with no rows here behaves exactly as before.
--
-- teacher_id is varchar to match sgs_teacher_master.teacher_id ('T02'). No FK:
-- the production tables are owned by swaispostgres, and data entry writes the
-- map before every teacher row exists.
--
-- Run on STAGING first, production with the release.

CREATE TABLE IF NOT EXISTS sgs_teacher_class_map (
    map_id           BIGSERIAL PRIMARY KEY,
    teacher_id       VARCHAR(50) NOT NULL,
    class_id         BIGINT      NOT NULL,
    section          VARCHAR(10) NOT NULL,
    subject_name     VARCHAR(150),
    is_class_teacher BOOLEAN     DEFAULT FALSE,
    record_status    VARCHAR(20) DEFAULT 'Active',
    created_at       TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_teacher_class_map_assignment
        UNIQUE (teacher_id, class_id, section, subject_name)
);

CREATE INDEX IF NOT EXISTS ix_sgs_teacher_class_map_teacher_id
    ON sgs_teacher_class_map (teacher_id);
CREATE INDEX IF NOT EXISTS ix_sgs_teacher_class_map_class_id
    ON sgs_teacher_class_map (class_id);

-- The app reads this; the admin dashboard writes it.
GRANT SELECT, INSERT, UPDATE, DELETE ON sgs_teacher_class_map TO swais_app_user;
GRANT USAGE, SELECT ON SEQUENCE sgs_teacher_class_map_map_id_seq TO swais_app_user;
