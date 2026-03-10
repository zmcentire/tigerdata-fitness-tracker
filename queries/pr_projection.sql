SELECT
    time_bucket('1 week', logged_at)             AS week,
    e.name                                        AS exercise,
    ROUND(MAX(weight_kg * (1 + reps / 30.0)), 2) AS best_e1rm_kg,
    ROUND(MAX(weight_kg * (1 + reps / 30.0)) * 2.205, 1) AS best_e1rm_lbs,
    EXTRACT(EPOCH FROM time_bucket('1 week', logged_at)) AS week_epoch
FROM workout_sets ws
JOIN exercises e ON e.id = ws.exercise_id
WHERE logged_at > NOW() - INTERVAL '16 weeks'
GROUP BY week, e.name
ORDER BY e.name, week ASC;