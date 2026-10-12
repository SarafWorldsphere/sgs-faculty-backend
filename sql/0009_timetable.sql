-- 0009: the class timetable.
--
-- Three features ask to display a timetable — the teacher's own week, the
-- student's class timetable, and the same shown to a parent — and none of them
-- can be built because no timetable exists anywhere in the platform.
--
-- Two tables rather than one:
--
--   sgs_period_master   what a period is and when it runs. The same for every
--                       class, and it changes twice a year, so it does not
--                       belong repeated on every slot.
--
--   sgs_timetable       one row per class-section, day and period.
--
-- The academic calendar switches to half-day timings on 15 March 2027 — six
-- periods instead of eight — which is a different set of times over the same
-- timetable of subjects. schedule_type carries that.
--
-- Run on STAGING first, production with the release.

-- ─────────────────────────────────────────────────────────────────────────
-- 1. Period definitions
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sgs_period_master (
    period_id      BIGSERIAL PRIMARY KEY,
    academic_year  VARCHAR(9)   NOT NULL,
    -- 'full' until 14 Mar 2027, 'half' from 15 Mar 2027
    schedule_type  VARCHAR(10)  NOT NULL DEFAULT 'full',
    -- Sequential including breaks, so the grid renders in order. Breaks carry
    -- is_teaching = false rather than being left out, or a timetable would
    -- show the lunch hour as a free period.
    period_no      INT          NOT NULL,
    period_label   VARCHAR(50)  NOT NULL,
    start_time     TIME         NOT NULL,
    end_time       TIME         NOT NULL,
    is_teaching    BOOLEAN      NOT NULL DEFAULT TRUE,
    record_status  VARCHAR(20)  DEFAULT 'Active',
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_period_master UNIQUE (academic_year, schedule_type, period_no)
);

-- ─────────────────────────────────────────────────────────────────────────
-- 2. The timetable itself
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sgs_timetable (
    timetable_id   BIGSERIAL PRIMARY KEY,
    academic_year  VARCHAR(9)   NOT NULL,
    class_id       BIGINT       NOT NULL,
    -- Must hold the same values as sgs_student_master.section, or the roll and
    -- the timetable describe different groups of children.
    section        VARCHAR(10)  NOT NULL,
    -- 1 = Monday … 6 = Saturday. No Sunday rows.
    day_of_week    INT          NOT NULL,
    period_no      INT          NOT NULL,
    subject_name   VARCHAR(150) NOT NULL,
    -- varchar to match sgs_teacher_master.teacher_id ('T02'). No FK: the
    -- production tables are owned by a different role.
    teacher_id     VARCHAR(50)  NOT NULL,
    record_status  VARCHAR(20)  DEFAULT 'Active',
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP,

    -- One class-section cannot have two subjects in the same period.
    CONSTRAINT uq_timetable_slot
        UNIQUE (academic_year, class_id, section, day_of_week, period_no),
    CONSTRAINT ck_timetable_day   CHECK (day_of_week BETWEEN 1 AND 6),
    CONSTRAINT ck_timetable_period CHECK (period_no >= 0)
);

CREATE INDEX IF NOT EXISTS ix_sgs_timetable_class
    ON sgs_timetable (academic_year, class_id, section);
CREATE INDEX IF NOT EXISTS ix_sgs_timetable_teacher
    ON sgs_timetable (academic_year, teacher_id);

-- NOTE: there is deliberately NO unique constraint on
-- (teacher_id, day_of_week, period_no). A teacher in two classrooms at once is
-- wrong, but two teachers sharing a lab period is legitimate, and a hard
-- constraint would block it. The Admin screen must check for the clash and
-- refuse it with a readable message. The query that finds one:
--
--   SELECT teacher_id, day_of_week, period_no, count(*)
--   FROM   sgs_timetable
--   WHERE  academic_year = '2026-27' AND record_status = 'Active'
--   GROUP BY teacher_id, day_of_week, period_no
--   HAVING count(*) > 1;

-- ─────────────────────────────────────────────────────────────────────────
-- 3. Permissions
-- ─────────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE, DELETE ON sgs_timetable     TO swais_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON sgs_period_master TO swais_app_user;
GRANT USAGE, SELECT ON SEQUENCE sgs_timetable_timetable_id_seq TO swais_app_user;
GRANT USAGE, SELECT ON SEQUENCE sgs_period_master_period_id_seq TO swais_app_user;

-- ─────────────────────────────────────────────────────────────────────────
-- 4. Period timings, from the Government academic calendar 2026-27
-- ─────────────────────────────────────────────────────────────────────────

INSERT INTO sgs_period_master
    (academic_year, schedule_type, period_no, period_label, start_time, end_time, is_teaching)
VALUES
    -- Full day, until 14 March 2027
    ('2026-27', 'full',  0, 'School Assembly', '09:05', '09:15', FALSE),
    ('2026-27', 'full',  1, '1st Period',      '09:15', '10:00', TRUE),
    ('2026-27', 'full',  2, '2nd Period',      '10:00', '10:40', TRUE),
    ('2026-27', 'full',  3, 'Short Break',     '10:40', '10:55', FALSE),
    ('2026-27', 'full',  4, '3rd Period',      '10:55', '11:35', TRUE),
    ('2026-27', 'full',  5, '4th Period',      '11:35', '12:15', TRUE),
    ('2026-27', 'full',  6, 'Lunch Break',     '12:15', '13:05', FALSE),
    ('2026-27', 'full',  7, '5th Period',      '13:05', '13:45', TRUE),
    ('2026-27', 'full',  8, 'Water Bell',      '13:45', '13:50', FALSE),
    ('2026-27', 'full',  9, '6th Period',      '13:50', '14:30', TRUE),
    ('2026-27', 'full', 10, 'Short Break',     '14:30', '14:40', FALSE),
    ('2026-27', 'full', 11, '7th Period',      '14:40', '15:20', TRUE),
    ('2026-27', 'full', 12, '8th Period',      '15:20', '16:00', TRUE),

    -- Half day, from 15 March 2027
    ('2026-27', 'half',  0, 'School Assembly', '07:50', '08:00', FALSE),
    ('2026-27', 'half',  1, '1st Period',      '08:00', '08:40', TRUE),
    ('2026-27', 'half',  2, '2nd Period',      '08:40', '09:20', TRUE),
    ('2026-27', 'half',  3, '3rd Period',      '09:20', '10:00', TRUE),
    ('2026-27', 'half',  4, 'Short Break',     '10:00', '10:30', FALSE),
    ('2026-27', 'half',  5, '4th Period',      '10:30', '11:10', TRUE),
    ('2026-27', 'half',  6, '5th Period',      '11:10', '11:50', TRUE),
    ('2026-27', 'half',  7, '6th Period',      '11:50', '12:30', TRUE)
ON CONFLICT ON CONSTRAINT uq_period_master DO NOTHING;
