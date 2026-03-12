import os
import csv
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode="require"
    )

def get_exercise_map(cur):
    """Returns dict of exercise name -> id, e.g. {'Bench Press': 1}"""
    cur.execute("SELECT id, name FROM exercises;")
    return {row[1]: row[0] for row in cur.fetchall()}

def parse_csv(filepath):
    """
    Reads a CSV file and returns a list of tuples ready for DB insert.

    Expected CSV columns:
    date, exercise, set_number, reps, weight_lbs, rpe, notes

    Example row:
    2026-03-08, Bench Press, 1, 5, 185, 8.0, felt strong
    """
    rows = []
    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "date":        row["date"].strip(),
                "exercise":    row["exercise"].strip(),
                "set_number":  int(row["set_number"]),
                "reps":        int(row["reps"]),
                "weight_lbs":  float(row["weight_lbs"]),
                "rpe":         float(row["rpe"]) if row["rpe"].strip() else None,
                "notes":       row["notes"].strip() if row["notes"].strip() else None
            })
    return rows

def insert_sets(rows, filepath=None):
    conn = get_connection()
    cur = conn.cursor()

    exercise_map = get_exercise_map(cur)
    db_rows = []

    for row in rows:
        exercise_name = row["exercise"]
        if exercise_name not in exercise_map:
            print(f"  ⚠ Unknown exercise '{exercise_name}' — skipping.")
            continue

        weight_kg = round(row["weight_lbs"] / 2.205, 2)

        db_rows.append((
            row["date"],
            exercise_map[exercise_name],
            row["set_number"],
            row["reps"],
            weight_kg,
            row["rpe"],
            row["notes"]
        ))

    if not db_rows:
        print("No valid rows to insert.")
        cur.close()
        conn.close()
        return

    try:
        cur.executemany("""
            INSERT INTO workout_sets
                (logged_at, exercise_id, set_number, reps, weight_kg, rpe, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, db_rows)
        conn.commit()
        print(f"✓ Inserted {len(db_rows)} sets from {filepath or 'input'}")
    except Exception as e:
        conn.rollback()
        print(f"✗ INSERT FAILED: {e}")
        print(f"  First row attempted: {db_rows[0] if db_rows else 'none'}")
    finally:
        cur.close()
        conn.close()

# --- Run directly to test ---
if __name__ == "__main__":
    rows = parse_csv("data/sample_workouts.csv")
    insert_sets(rows, "data/sample_workouts.csv")
