import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    sslmode="require"         # required for Tiger Cloud
)

cur = conn.cursor()
cur.execute("SELECT version();")
print(cur.fetchone())         # Should print PostgreSQL version string

cur.execute("SELECT default_version FROM pg_available_extensions WHERE name = 'timescaledb';")
print("TimescaleDB version:", cur.fetchone())

cur.close()
conn.close()