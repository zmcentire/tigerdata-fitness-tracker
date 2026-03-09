import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    sslmode="require"
)

cur = conn.cursor()

sessions = [
    # (days_ago, exercise_id, sets)
    # Week 3 ago
    (21, 1, [(1,5,80), (2,5,80), (3,5,80), (4,3,85)]),   # Bench
    (20, 2, [(1,5,120),(2,5,120),(3,5,120),(4,3,125)]),   # Squat
    (19, 3, [(1,5,150),(2,5,150),(3,3,155)]),              # Deadlift
    # Week 2 ago
    (14, 1, [(1,5,82.5),(2,5,82.5),(3,5,82.5),(4,3,87.5)]),
    (13, 2, [(1,5,122.5),(2,5,122.5),(3,5,122.5)]),
    (12, 3, [(1,5,152.5),(2,5,152.5),(3,3,157.5)]),
    # Week 1 ago
    (7,  1, [(1,5,85),(2,5,85),(3,5,85),(4,3,90)]),
    (6,  2, [(1,5,125),(2,5,125),(3,5,125),(4,2,130)]),
    (5,  3, [(1,5,155),(2,5,155),(3,3,160)]),
]

rows = []
for (days_ago, exercise_id, sets) in sessions:
    session_time = datetime.now() - timedelta(days=days_ago)
    for (set_num, reps, weight) in sets:
        rpe = round(random.uniform(7.0, 9.0), 1)
        rows.append((
            session_time,
            exercise_id,
            set_num,
            reps,
            weight,
            rpe,
            None
        ))

cur.executemany("""
    INSERT INTO workout_sets
        (logged_at, exercise_id, set_number, reps, weight_kg, rpe, notes)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
""", rows)

conn.commit()
print(f"Seeded {len(rows)} sets across {len(sessions)} sessions.")

cur.close()
conn.close()