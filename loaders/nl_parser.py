import os
import json
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from loaders.log_parser import insert_sets, get_connection

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a fitness data parser. The user will describe a workout
in plain English. Extract the sets and return ONLY a valid JSON array.

Each object in the array must have these exact keys:
- date: today's date as YYYY-MM-DD string
- exercise: one of exactly "Bench Press", "Squat", or "Deadlift"
- set_number: integer starting at 1
- reps: integer
- weight_lbs: float (convert from kg if needed)
- rpe: float between 1-10, or null if not mentioned
- notes: string or null

Rules:
- If the user says "3x5 at 185", that means 3 sets of 5 reps at 185 lbs — expand into 3 objects
- If no RPE is mentioned, set rpe to null
- Return ONLY the JSON array, no explanation, no markdown, no backticks"""

def parse_natural_language(text: str, date: str = None) -> list:
    """
    Converts plain English workout description to structured list of sets.

    Example inputs:
    - "Benched 185 for 3 sets of 5 at RPE 8"
    - "Hit a heavy single on deadlift — 255lbs at RPE 9.5"
    - "Squatted 225x3x3, last set RPE 8.5"
    """
    today = date or datetime.now().strftime("%Y-%m-%d")

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Today is {today}. Parse this workout: {text}"}
        ]
    )

    raw = message.content[0].text.strip()

    try:
        sets = json.loads(raw)
        print(f"  Parsed {len(sets)} sets from: \"{text}\"")
        return sets
    except json.JSONDecodeError as e:
        print(f"  ✗ Failed to parse JSON response: {e}")
        print(f"  Raw response was: {raw}")
        return []

def log_workout_from_text(text: str, date: str = None):
    """Full pipeline: natural language → parse → insert into hypertable"""
    sets = parse_natural_language(text, date)
    if sets:
        insert_sets(sets)
    else:
        print("  No sets to insert.")

# --- Run directly to test ---
if __name__ == "__main__":
    # Add your Anthropic API key to .env first:
    # ANTHROPIC_API_KEY=sk-ant-...

    test_inputs = [
        "Benched 185lbs for 3 sets of 5 at RPE 8",
        "Squatted 225 for 3x3, last set was RPE 9",
        "Pulled 255 on deadlift for a single at RPE 8.5"
    ]

    for text in test_inputs:
        print(f"\nInput: {text}")
        log_workout_from_text(text)