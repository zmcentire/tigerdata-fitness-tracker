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