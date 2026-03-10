SELECT DISTINCT ON (e.name)
    e.name                                          AS exercise,
    logged_at::date                                 AS date_achieved,
    weight_kg                                       AS weight_kg,
    ROUND(weight_kg * 2.205, 1)                    AS weight_lbs,
    reps,
    rpe,
    ROUND(weight_kg * (1 + reps / 30.0), 2)       AS best_e1rm_kg,
    ROUND(weight_kg * (1 + reps / 30.0) * 2.205, 1) AS best_e1rm_lbs
FROM workout_sets ws
JOIN exercises e ON e.id = ws.exercise_id
ORDER BY e.name, (weight_kg * (1 + reps / 30.0)) DESC;