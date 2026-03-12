ALTER TABLE workout_sets SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'exercise_id',
    timescaledb.compress_orderby   = 'logged_at DESC'
);

SELECT hypertable_name,
       compression_enabled
FROM timescaledb_information.hypertables
WHERE hypertable_name = 'workout_sets';

SELECT add_compression_policy('workout_sets',
    compress_after => INTERVAL '30 days'
);

SELECT job_id,
       application_name,
       schedule_interval,
       next_start,
       scheduled,
       config
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_compression';

SELECT compress_chunk(c)
FROM show_chunks('workout_sets') c;

SELECT chunk_name,
       before_compression_total_bytes,
       after_compression_total_bytes,
       ROUND(
           (1 - after_compression_total_bytes::numeric /
                before_compression_total_bytes) * 100, 1
       ) AS compression_pct
FROM chunk_compression_stats('workout_sets')
WHERE compression_status = 'Compressed'
ORDER BY chunk_name;

SELECT add_retention_policy('workout_sets',
    drop_after => INTERVAL '1 year'
);

SELECT add_retention_policy('pr_records',
    drop_after => INTERVAL '2 years'
);


-- Complete view of all active policies
SELECT
    job_id,
    application_name,
    proc_name,
    schedule_interval,
    scheduled,
    hypertable_name,
    config
FROM timescaledb_information.jobs
WHERE proc_name IN (
    'policy_compression',
    'policy_retention',
    'policy_refresh_continuous_aggregate'
)
ORDER BY proc_name, hypertable_name;