SELECT
    time_bucket('1 week', logged_at)        AS week,
    e.name                                   AS exercise,
    MAX(weight_kg * (1 + reps / 30.0))      AS best_e1rm_kg,
    ROUND(MAX(weight_kg * (1 + reps / 30.0)) * 2.205, 1) AS best_e1rm_lbs,
    MAX(weight_kg)                           AS top_weight_kg,
    ROUND(MAX(weight_kg) * 2.205, 1)        AS top_weight_lbs,
    COUNT(*)                                 AS total_sets,
    ROUND(AVG(rpe), 1)                      AS avg_rpe
FROM workout_sets ws
JOIN exercises e ON e.id = ws.exercise_id
WHERE logged_at > NOW() - INTERVAL '12 weeks'
GROUP BY week, e.name
ORDER BY week DESC, e.name;