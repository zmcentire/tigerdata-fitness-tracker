-- ================================================
-- 002_create_continuous_aggregates.sql
-- TigerData Fitness Tracker
-- ================================================

-- Weekly best estimated 1RM per lift
-- Auto-refreshes in background as new sets are logged
CREATE MATERIALIZED VIEW weekly_1rm
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 week', logged_at)                    AS week,
    exercise_id,
    MAX(weight_kg * (1 + reps / 30.0))                 AS best_e1rm_kg,
    ROUND(
        MAX(weight_kg * (1 + reps / 30.0)) * 2.205, 1
    )                                                   AS best_e1rm_lbs,
    MAX(
        CASE WHEN reps <= 10
        THEN weight_kg * 36.0 / (37 - reps)
        END
    )                                                   AS best_e1rm_brzycki_kg,
    MAX(weight_kg)                                      AS top_weight_kg,
    COUNT(*)                                            AS total_sets,
    ROUND(AVG(rpe), 2)                                  AS avg_rpe
FROM workout_sets
GROUP BY week, exercise_id
WITH DATA;

-- Enable real-time aggregation (required on TimescaleDB v2.13+)
ALTER MATERIALIZED VIEW weekly_1rm
SET (timescaledb.materialized_only = false);

-- Daily refresh policy for weekly_1rm
SELECT add_continuous_aggregate_policy('weekly_1rm',
    start_offset      => INTERVAL '12 weeks',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 day'
);

-- ------------------------------------------------
-- Hierarchical aggregate: 4-week rollup on top of weekly_1rm
-- Uses '4 weeks' not '1 month' — required for bucket compatibility
CREATE MATERIALIZED VIEW monthly_1rm
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('4 weeks', week)         AS month,
    exercise_id,
    MAX(best_e1rm_kg)                    AS best_e1rm_kg,
    ROUND(MAX(best_e1rm_kg) * 2.205, 1) AS best_e1rm_lbs,
    SUM(total_sets)                      AS total_sets,
    ROUND(AVG(avg_rpe), 2)              AS avg_rpe
FROM weekly_1rm
GROUP BY month, exercise_id
WITH DATA;

-- Weekly refresh policy for monthly_1rm
SELECT add_continuous_aggregate_policy('monthly_1rm',
    start_offset      => INTERVAL '48 weeks',
    end_offset        => INTERVAL '2 weeks',
    schedule_interval => INTERVAL '1 week'
);