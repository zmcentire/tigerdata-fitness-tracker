# TigerData Fitness Tracker

An agentic powerlifting tracker built on TimescaleDB (TigerData), FastAPI, and Claude.
Tracks workout sets as time-series data, projects 1RM progress toward 2026 PR targets,
and provides an AI coaching interface powered by tool-use agents.

## Architecture
```
NL text input
    ↓ Claude API (nl_parser)
workout_sets hypertable
    ↓ TimescaleDB continuous aggregate (weekly refresh)
weekly_1rm → monthly_1rm
    ↓ numpy linear regression (pr_projector)
PR projections + next session plans
    ↓ FastAPI HTTP endpoints
Streamlit dashboard
```

## TimescaleDB Features Used

| Feature | Implementation |
|---|---|
| Hypertables | `workout_sets`, `pr_records` — auto-partitioned by time |
| Continuous Aggregates | `weekly_1rm`, `monthly_1rm` — hierarchical, incremental refresh |
| Compression | `workout_sets` chunks compressed after 30 days |
| Retention Policy | Raw sets dropped after 1 year, PR records after 2 years |
| time_bucket() | Weekly and 4-week rollups with chunk pruning |
| Refresh Policies | Daily for weekly_1rm, weekly for monthly_1rm |

## 2026 PR Targets

| Lift | Current e1RM | Target | Gap |
|---|---|---|---|
| Bench Press | 215.8 lbs | 225 lbs | -9.2 lbs |
| Squat | 247.5 lbs | 315 lbs | -67.5 lbs |
| Deadlift | 263.5 lbs | 285 lbs | -21.5 lbs |

## Project Structure
```
tigerdata-fitness-tracker/
├── schema/
│   ├── 001_create_hypertables.sql        # Hypertables + indexes
│   ├── 002_create_continuous_aggregates.sql  # weekly_1rm, monthly_1rm
│   └── 003_compression_retention.sql     # Compression + retention policies
├── loaders/
│   ├── log_parser.py                     # CSV ingestion pipeline
│   └── nl_parser.py                      # NL → Claude → structured sets
├── agents/
│   ├── pr_projector.py                   # Linear regression PR projections
│   └── fitness_agent.py                  # Claude tool-use agent (4 tools)
├── api/
│   └── main.py                           # FastAPI — 5 endpoints
├── data/
│   ├── seed.py                           # 32 sets across 9 sessions
│   └── sample_workouts.csv
├── queries/
│   ├── lift_history.sql
│   ├── best_1rm.sql
│   └── pr_projection.sql
├── tests/
│   └── test_1rm_formulas.py              # pytest — 20+ unit tests
├── dashboard.py                          # Streamlit dashboard
├── Dockerfile.api
├── Dockerfile.dashboard
├── docker-compose.yml
└── requirements.txt
```

## Quick Start

### Local development
```bash
# 1. Clone and set up environment
git clone https://github.com/zmcentire/tigerdata-fitness-tracker
cd tigerdata-fitness-tracker
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env with your TigerData connection details and Anthropic API key

# 3. Run the FastAPI backend
python api/main.py

# 4. Run the Streamlit dashboard (new terminal)
streamlit run dashboard.py

# 5. Run tests
pytest tests/ -v
```

### Docker
```bash
# Build and start both services
docker compose up --build

# Dashboard: http://localhost:8501
# API docs:  http://localhost:8000/docs

# Stop
docker compose down
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/log` | Log workout from natural language |
| GET | `/trend/{lift}` | Weekly e1RM trend from continuous aggregate |
| GET | `/projection/{lift}` | Linear regression PR projection |
| GET | `/next-session/{lift}` | RPE-based next session recommendation |
| POST | `/chat` | Stateless agentic chat with tool use |

## Agent Tools

The Claude-powered coach has 4 tools that query TimescaleDB directly:

- `log_workout` — parses NL text and inserts into `workout_sets` hypertable
- `get_pr_projection` — reads from `weekly_1rm` continuous aggregate, runs regression
- `get_next_session` — reads last session RPE, applies double progression rules
- `get_full_report` — combines all three lifts into a single coaching report

## Database Schema
```sql
-- Hypertables
workout_sets (logged_at, exercise_id, set_number, reps, weight_kg, rpe, notes)
pr_records   (recorded_at, exercise_id, estimated_1rm_kg, formula, notes)

-- Regular tables
exercises  (id, name, category)
pr_targets (id, exercise_id, target_1rm_kg, target_date)

-- Continuous aggregates
weekly_1rm  (week, exercise_id, best_e1rm_kg, best_e1rm_lbs, total_sets, avg_rpe)
monthly_1rm (month, exercise_id, best_e1rm_kg, best_e1rm_lbs, total_sets, avg_rpe)
```

## Running Tests
```bash
pytest tests/ -v
```

Tests cover: Epley formula, Brzycki formula, unit conversions,
double progression logic, and PR target validation.
No database connection required — pure unit tests.