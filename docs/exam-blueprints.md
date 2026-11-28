# Exam blueprints — changing a school's test types

The Auto Test screen's test types, their question mixes and the competitive
patterns are held per school in three tables. Before migration `0012` they
were constants in the faculty frontend, identical for every tenant and only
changeable by a deploy.

| Table | Holds |
|---|---|
| `exam_blueprint` | one row per test type — weekly, ct, pt, term, competitive |
| `exam_blueprint_row` | that type's question mix: how many of each type, marks each |
| `exam_pattern` | competitive patterns — NTSE, NMMS, olympiads, custom |

All three are tenant-scoped with forced row-level security and a
`stamp_tenant` trigger, so `tenant_id` is filled automatically on insert from
`app.tenant_id`.

**This should eventually be an admin screen.** `GET /api/v1/exam-blueprints`
already returns the right shape; it needs the write side and a UI under School
Admin. Until then these are run by hand by whoever holds the `swaispostgres`
password.

---

## Before you start

```sql
-- Which school is which
SELECT tenant_id, domain FROM platform.tenant_domains;

\set tenant 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
SET app.tenant_id = :'tenant';     -- the stamp trigger reads this on insert
```

> **`swaispostgres` bypasses row-level security.**
>
> A superuser ignores RLS even when it is `FORCE`d. So the policies give you
> no protection in a `psql` session: every statement must name `tenant_id`
> explicitly. Relying on the policy to scope a lookup is what broke the first
> run of migration `0012` — a lookup returned the *other* school's
> `blueprint_id` and the foreign key refused it.

---

## A. Add a new test type

A 25-mark unit test, 15 multiple choice plus 5 short answers.

```sql
BEGIN;

INSERT INTO exam_blueprint
  (code, label, short_label, note, total_marks, minutes, group_name, exam_type, display_seq)
VALUES
  ('unit', 'Unit test', 'unit test', '25 marks · 1 chapter', 25, 45, 'school', 'Unit', 6);

INSERT INTO exam_blueprint_row (blueprint_id, question_type, question_count, marks_each, display_seq)
SELECT b.blueprint_id, v.qt, v.cnt, v.each, v.seq
FROM exam_blueprint b
JOIN (VALUES
        ('mcq',   15, 1.0, 1),
        ('short',  5, 2.0, 2)
     ) AS v(qt, cnt, each, seq) ON true
WHERE b.code = 'unit' AND b.tenant_id = :'tenant';

COMMIT;
```

## B. Change an existing one

This school's class test is 15 marks, not 12.5.

```sql
BEGIN;

UPDATE exam_blueprint SET total_marks = 15
 WHERE code = 'ct' AND tenant_id = :'tenant';

UPDATE exam_blueprint_row r SET question_count = 10
  FROM exam_blueprint b
 WHERE r.blueprint_id = b.blueprint_id
   AND b.code = 'ct' AND b.tenant_id = :'tenant'
   AND r.question_type = 'mcq';

COMMIT;
```

## C. Seed a brand new school

Only needed if they want something different from the defaults — see
"A school with no rows" below.

```sql
\set src 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
\set new '<new tenant uuid>'
SET app.tenant_id = :'new';

BEGIN;

INSERT INTO exam_blueprint
  (code,label,short_label,note,total_marks,minutes,group_name,exam_type,numbered,display_seq)
SELECT code,label,short_label,note,total_marks,minutes,group_name,exam_type,numbered,display_seq
FROM exam_blueprint WHERE tenant_id = :'src';

INSERT INTO exam_blueprint_row (blueprint_id,question_type,question_count,marks_each,display_seq)
SELECT nb.blueprint_id, r.question_type, r.question_count, r.marks_each, r.display_seq
FROM exam_blueprint_row r
JOIN exam_blueprint ob ON ob.blueprint_id = r.blueprint_id AND ob.tenant_id = :'src'
JOIN exam_blueprint nb ON nb.code = ob.code AND nb.tenant_id = :'new';

INSERT INTO exam_pattern (code,label,target,question_count,marks_each,minutes,display_seq)
SELECT code,label,target,question_count,marks_each,minutes,display_seq
FROM exam_pattern WHERE tenant_id = :'src';

COMMIT;
```

## D. Competitive patterns

These only prefill numbers on the Configure screen.

```sql
INSERT INTO exam_pattern (code, label, target, question_count, marks_each, minutes, display_seq)
VALUES ('jnv', 'JNV selection practice', 'JNV', 80, 1.0, 120, 6);
```

`target` is sent to the AI service as the exam type.

---

## Always check afterwards

```sql
SELECT b.code, b.total_marks,
       sum(r.question_count * r.marks_each) AS blueprint_adds_up
FROM exam_blueprint b
LEFT JOIN exam_blueprint_row r ON r.blueprint_id = b.blueprint_id
WHERE b.tenant_id = :'tenant'
GROUP BY b.code, b.total_marks
ORDER BY b.code;
```

**The two columns must match.** The Configure screen only enables Generate
when the blueprint balances against the total, so a type whose rows do not add
up to `total_marks` is selectable but leaves the button permanently disabled
with nothing on screen explaining why. This is the most likely mistake when
editing by hand.

---

## Rules worth knowing

**The seven question types are fixed in code.** `mcq`, `fill`, `truefalse`,
`oneword`, `short`, `match`, `long`. They are referenced here by code because
the printed paper's section order and answer-space rendering are built around
them. An unknown value is accepted by the database and then silently skipped
by the paper — no error, just a missing section.

**Do not delete rows — set `is_active = false`.** Saved papers reference them.

**A school with no rows is fine.** The faculty app falls back to its five
built-in defaults when the API returns nothing, so a new tenant works without
being seeded. Case C is only for a school that wants something different.

**`display_seq`** controls the order the tiles appear in on the Configure
screen, for both blueprints and patterns.

**`numbered`** is a JSON array for types that come in a series, e.g.
`'["PT-1","PT-2","PT-3","PT-4"]'::jsonb`. Leave it null otherwise.

**`group_name`** is `school` or `competitive`. The screen groups the tiles by
it, and `competitive` switches the form to asking for a question count rather
than a blueprint.

---

## What the API returns

`GET /api/v1/exam-blueprints`, scoped to the caller's school:

```json
{
  "testTypes": [
    { "id": "weekly", "label": "Weekly test", "totalMarks": 10, "minutes": 30,
      "group": "school", "examType": "Weekly", "numbered": null,
      "blueprint": { "mcq": [5, 1], "truefalse": [3, 1], "short": [1, 2] } }
  ],
  "examPatterns": [
    { "id": "ntse", "label": "NTSE — stage 1 practice", "target": "NTSE",
      "questions": 50, "marks": 1, "minutes": 45 }
  ],
  "configured": true
}
```

`configured: false` means this school has no rows and the app is using its
built-in defaults.
