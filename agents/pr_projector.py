import os
import numpy as np
import psycopg2
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# Your 2026 PR targets in lbs (matches what's in pr_targets table)
PR_TARGETS_LBS = {
    "Bench Press": 225.0,
    "Squat":       315.0,
    "Deadlift":    285.0
}

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode="require"
    )

def get_1rm_trend(exercise_name: str, weeks: int = 8) -> list[dict]:
    """
    Pulls weekly best e1RM from the continuous aggregate view.
    Returns list of dicts ordered oldest → newest for regression.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            w.week,
            w.best_e1rm_kg,
            ROUND(w.best_e1rm_kg * 2.205, 1)      AS best_e1rm_lbs,
            EXTRACT(EPOCH FROM w.week)::FLOAT       AS week_epoch,
            w.total_sets,
            w.avg_rpe
        FROM weekly_1rm w
        JOIN exercises e ON e.id = w.exercise_id
        WHERE e.name = %s
          AND w.week >= NOW() - (%s || ' weeks')::INTERVAL
        ORDER BY w.week ASC;
    """, (exercise_name, str(weeks)))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "week":          row[0],
            "e1rm_kg":       float(row[1]),
            "e1rm_lbs":      float(row[2]),
            "week_epoch":    row[3],
            "total_sets":    row[4],
            "avg_rpe":       float(row[5]) if row[5] else None
        }
        for row in rows
    ]

def project_1rm(
    exercise_name: str,
    target_date: date = None,
    weeks: int = 8
) -> dict:
    """
    Fits a linear regression to the weekly 1RM trend and
    projects to the target date (defaults to end of current month).

    Returns a dict with current e1RM, projected e1RM, trend slope,
    target, and on_track boolean.
    """
    if target_date is None:
        # Default: end of current month
        today = date.today()
        if today.month == 12:
            target_date = date(today.year + 1, 1, 1)
        else:
            target_date = date(today.year, today.month + 1, 1)

    trend = get_1rm_trend(exercise_name, weeks)

    if len(trend) < 2:
        return {
            "exercise":       exercise_name,
            "error":          f"Not enough data — need at least 2 weeks, got {len(trend)}",
            "data_points":    len(trend)
        }

    # Build X (week timestamps as floats) and Y (e1RM in lbs) arrays
    x = np.array([row["week_epoch"] for row in trend])
    y = np.array([row["e1rm_lbs"]   for row in trend])

    # Fit linear regression: y = slope * x + intercept
    coeffs     = np.polyfit(x, y, 1)
    slope      = float(coeffs[0])
    intercept  = float(coeffs[1])

    # Project to target date
    target_epoch    = datetime.combine(target_date, datetime.min.time()).timestamp()
    projected_lbs   = float(slope * target_epoch + intercept)

    # Current best e1RM (most recent week)
    current_lbs     = float(trend[-1]["e1rm_lbs"])
    target_lbs      = PR_TARGETS_LBS.get(exercise_name, 0)

    # Weekly rate of gain in lbs
    seconds_per_week = 7 * 24 * 3600
    weekly_gain_lbs  = slope * seconds_per_week

    # Weeks remaining to target date
    weeks_remaining  = (target_date - date.today()).days / 7

    on_track = projected_lbs >= target_lbs

    return {
        "exercise":         exercise_name,
        "current_e1rm_lbs": round(current_lbs, 1),
        "projected_e1rm_lbs": round(projected_lbs, 1),
        "target_lbs":       target_lbs,
        "target_date":      target_date.isoformat(),
        "weekly_gain_lbs":  round(weekly_gain_lbs, 2),
        "weeks_remaining":  round(weeks_remaining, 1),
        "on_track":         on_track,
        "data_points":      len(trend),
        "trend":            trend
    }

def project_all_lifts(target_date: date = None) -> dict:
    """Run projection for all three compound lifts."""
    results = {}
    for lift in ["Bench Press", "Squat", "Deadlift"]:
        results[lift] = project_1rm(lift, target_date)
    return results

def write_projection_to_db(projection: dict):
    """
    Write the projection result back to pr_records hypertable.
    This makes your projections themselves time-series queryable.
    """
    if "error" in projection:
        return

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id FROM exercises WHERE name = %s
    """, (projection["exercise"],))
    row = cur.fetchone()
    if not row:
        print(f"  Exercise not found: {projection['exercise']}")
        cur.close()
        conn.close()
        return

    exercise_id = row[0]

    cur.execute("""
    INSERT INTO pr_records
        (recorded_at, exercise_id, estimated_1rm_kg, formula, notes)
    VALUES
        (NOW(), %s, %s, %s, %s)
    """, (
    exercise_id,
    float(round(projection["projected_e1rm_lbs"] / 2.205, 2)),
    'linear_projection',
    f"Projected to {projection['target_date']} — "
    f"weekly gain: {projection['weekly_gain_lbs']} lbs/week"
    ))

    conn.commit()
    cur.close()
    conn.close()

def print_projection_report(results: dict):
    """Pretty-print the full projection report to terminal."""
    print("\n" + "="*60)
    print("  2026 PR PROJECTION REPORT")
    print("="*60)

    for lift, proj in results.items():
        print(f"\n  {lift.upper()}")
        print(f"  {'─'*40}")

        if "error" in proj:
            print(f"  ⚠ {proj['error']}")
            continue

        status = "✅ ON TRACK" if proj["on_track"] else "❌ BEHIND PACE"
        print(f"  Status:          {status}")
        print(f"  Current e1RM:    {proj['current_e1rm_lbs']} lbs")
        print(f"  Projected e1RM:  {proj['projected_e1rm_lbs']} lbs")
        print(f"  Target:          {proj['target_lbs']} lbs by {proj['target_date']}")
        print(f"  Weekly gain:     +{proj['weekly_gain_lbs']} lbs/week")
        print(f"  Weeks remaining: {proj['weeks_remaining']}")
        print(f"  Data points:     {proj['data_points']} weeks")

    print("\n" + "="*60 + "\n")

def get_next_session(exercise_name: str) -> dict:
    """
    Looks at the last session's sets for a lift and applies
    double progression rules to recommend next session weights/reps.

    Rules:
    - RPE <= 7.5: increase weight by 5 lbs (aggressive jump)
    - RPE 7.5–8.5: increase weight by 2.5 lbs (standard progression)
    - RPE 8.5–9.5: keep weight, add 1 rep to each set
    - RPE > 9.5: keep weight and reps (consolidation week)
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ws.set_number,
            ws.reps,
            ws.weight_kg,
            ROUND(ws.weight_kg * 2.205, 1)          AS weight_lbs,
            ws.rpe,
            ws.logged_at::date                       AS session_date,
            ROUND(ws.weight_kg * (1 + ws.reps / 30.0) * 2.205, 1) AS e1rm_lbs
        FROM workout_sets ws
        JOIN exercises e ON e.id = ws.exercise_id
        WHERE e.name = %s
        ORDER BY ws.logged_at DESC
        LIMIT 5;
    """, (exercise_name,))

    last_sets = cur.fetchall()
    cur.close()
    conn.close()

    if not last_sets:
        return {"exercise": exercise_name, "error": "No previous sessions found"}

    avg_rpe = sum(s[4] for s in last_sets if s[4]) / len([s for s in last_sets if s[4]])
    last_weight_lbs = float(last_sets[0][3])
    last_weight_kg  = float(last_sets[0][2])
    last_reps       = last_sets[0][1]
    session_date    = last_sets[0][5]

    if avg_rpe <= 7.5:
        next_weight_lbs = round(last_weight_lbs + 5.0, 1)
        next_reps       = last_reps
        reason          = f"RPE {avg_rpe:.1f} <= 7.5 → aggressive +5 lbs"
    elif avg_rpe <= 8.5:
        next_weight_lbs = round(last_weight_lbs + 2.5, 1)
        next_reps       = last_reps
        reason          = f"RPE {avg_rpe:.1f} 7.5-8.5 → standard +2.5 lbs"
    elif avg_rpe <= 9.5:
        next_weight_lbs = last_weight_lbs
        next_reps       = last_reps + 1
        reason          = f"RPE {avg_rpe:.1f} 8.5-9.5 → same weight, +1 rep"
    else:
        next_weight_lbs = last_weight_lbs
        next_reps       = last_reps
        reason          = f"RPE {avg_rpe:.1f} > 9.5 → consolidation, hold position"

    next_weight_kg = round(next_weight_lbs / 2.205, 2)

    warmup_sets = [
        {"set": 1, "weight_lbs": round(next_weight_lbs * 0.5),  "reps": 5,  "note": "warmup"},
        {"set": 2, "weight_lbs": round(next_weight_lbs * 0.7),  "reps": 3,  "note": "warmup"},
        {"set": 3, "weight_lbs": round(next_weight_lbs * 0.85), "reps": 2,  "note": "warmup"},
    ]
    working_sets = [
        {"set": i, "weight_lbs": next_weight_lbs, "reps": next_reps, "note": "working"}
        for i in range(4, 7)
    ]

    return {
        "exercise":           exercise_name,
        "last_session":       str(session_date),
        "last_weight_lbs":    last_weight_lbs,
        "last_reps":          last_reps,
        "avg_rpe":            round(avg_rpe, 1),
        "next_weight_lbs":    next_weight_lbs,
        "next_weight_kg":     next_weight_kg,
        "next_reps":          next_reps,
        "progression_reason": reason,
        "warmup_sets":        warmup_sets,
        "working_sets":       working_sets
    }

# --- Run directly to test ---
if __name__ == "__main__":
    print("Pulling 1RM trend from weekly_1rm continuous aggregate...")
    results = project_all_lifts()

    print_projection_report(results)

    # Write projections back to pr_records hypertable
    print("Writing projections to pr_records...")
    for lift, proj in results.items():
        write_projection_to_db(proj)
        if "error" not in proj:
            print(f"  ✓ Saved projection for {lift}")
