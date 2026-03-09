CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

CREATE TABLE exercises (
    id       SERIAL PRIMARY KEY,
    name     TEXT   NOT NULL UNIQUE,
    category TEXT   NOT NULL
);

INSERT INTO exercises (name, category) VALUES
    ('Bench Press', 'push'),
    ('Squat',       'legs'),
    ('Deadlift',    'pull');

CREATE TABLE workout_sets (
    logged_at   TIMESTAMPTZ  NOT NULL,
    exercise_id INTEGER      NOT NULL REFERENCES exercises(id),
    set_number  SMALLINT     NOT NULL,
    reps        SMALLINT     NOT NULL,
    weight_kg   NUMERIC(6,2) NOT NULL,
    rpe         NUMERIC(3,1),
    notes       TEXT
);

SELECT create_hypertable('workout_sets', by_range('logged_at'));

CREATE TABLE pr_targets (
    id            SERIAL PRIMARY KEY,
    exercise_id   INTEGER      NOT NULL REFERENCES exercises(id),
    target_1rm_kg NUMERIC(6,2) NOT NULL,
    target_date   DATE         NOT NULL,
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);

INSERT INTO pr_targets (exercise_id, target_1rm_kg, target_date) VALUES
    (1, 102.1, '2026-12-31'),
    (2, 142.9, '2026-12-31'),
    (3, 129.3, '2026-12-31');

CREATE INDEX ON workout_sets (exercise_id, logged_at DESC);

CREATE TABLE pr_records (
    recorded_at      TIMESTAMPTZ  NOT NULL,
    exercise_id      INTEGER      NOT NULL REFERENCES exercises(id),
    estimated_1rm_kg NUMERIC(6,2),
    actual_1rm_kg    NUMERIC(6,2),
    formula          TEXT,
    notes            TEXT
);

SELECT create_hypertable('pr_records', by_range('recorded_at'));