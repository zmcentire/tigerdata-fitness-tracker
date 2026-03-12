import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from loaders.nl_parser import log_workout_from_text
from agents.pr_projector import project_1rm, project_all_lifts, get_next_session
from agents.fitness_agent import chat

# ── App setup ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="TigerData Fitness Tracker API",
    description=(
        "FastAPI layer over TimescaleDB hypertables. "
        "Exposes workout logging, 1RM trend queries from continuous "
        "aggregates, PR projections, and an agentic chat interface."
    ),
    version="1.0.0"
)

# Allow Streamlit (running on port 8501) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic models ──────────────────────────────────────────────────────────
# These define the shape of request and response bodies.
# FastAPI validates incoming JSON against these automatically.

class LogRequest(BaseModel):
    text: str
    # Example: {"text": "Benched 185 for 3x5 at RPE 8"}

class ChatRequest(BaseModel):
    message: str
    history: list = []
    # history is the full conversation so far — Streamlit tracks this in session state

class ChatResponse(BaseModel):
    response: str
    history: list

# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """
    Simple liveness check. Streamlit calls this on startup to confirm
    the API is reachable before rendering the dashboard.
    """
    return {"status": "ok", "service": "tigerdata-fitness-tracker"}


@app.post("/log")
def log_workout(req: LogRequest):
    """
    Accepts plain English workout description and inserts parsed sets
    into the workout_sets hypertable via the nl_parser pipeline.

    The continuous aggregate (weekly_1rm) will reflect the new data
    on its next scheduled refresh.

    Example request:
        POST /log
        {"text": "Squatted 225 for 3x5 at RPE 8"}
    """
    try:
        log_workout_from_text(req.text)
        return {
            "status":  "logged",
            "message": f"Workout logged: '{req.text}'"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trend/{lift}")
def get_trend(lift: str, weeks: int = 12):
    """
    Returns weekly best estimated 1RM trend for a given lift,
    queried directly from the weekly_1rm continuous aggregate view.

    This is the core TimescaleDB demo endpoint — data comes from
    the pre-materialized aggregate, not from scanning raw rows.

    Path params:
        lift: 'Bench Press', 'Squat', or 'Deadlift'
    Query params:
        weeks: number of weeks of history to return (default 12)

    Example: GET /trend/Bench%20Press?weeks=8
    """
    valid_lifts = ["Bench Press", "Squat", "Deadlift"]
    if lift not in valid_lifts:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid lift '{lift}'. Must be one of: {valid_lifts}"
        )
    try:
        from agents.pr_projector import get_1rm_trend
        trend = get_1rm_trend(lift, weeks=weeks)
        if not trend:
            return {"lift": lift, "weeks": weeks, "data": []}
        return {"lift": lift, "weeks": weeks, "data": trend}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projection/{lift}")
def get_projection(lift: str):
    """
    Returns PR projection for a given lift using linear regression
    on weekly_1rm continuous aggregate data.

    Returns current e1RM, projected e1RM at target date,
    weekly gain rate, on_track status, and data point count.

    Example: GET /projection/Squat
    """
    valid_lifts = ["Bench Press", "Squat", "Deadlift", "all"]
    if lift not in valid_lifts:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid lift. Must be one of: {valid_lifts}"
        )
    try:
        if lift == "all":
            result = project_all_lifts()
        else:
            result = project_1rm(lift)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/next-session/{lift}")
def next_session(lift: str):
    """
    Returns recommended warmup and working sets for the next
    session of a given lift, based on RPE-driven double progression.

    Reads last session from workout_sets hypertable and applies:
    - RPE <= 7.5:  +5 lbs
    - RPE 7.5-8.5: +2.5 lbs
    - RPE 8.5-9.5: same weight, +1 rep
    - RPE > 9.5:   hold position

    Example: GET /next-session/Deadlift
    """
    valid_lifts = ["Bench Press", "Squat", "Deadlift"]
    if lift not in valid_lifts:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid lift. Must be one of: {valid_lifts}"
        )
    try:
        result = get_next_session(lift)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    Stateless chat endpoint. The client (Streamlit) sends the full
    conversation history with each request. FastAPI passes it to the
    fitness agent, which calls TimescaleDB tools as needed, then
    returns the agent's response and updated history.

    This is stateless by design — conversation state lives in
    Streamlit's session_state, not on the server.

    Example request:
        POST /chat
        {
            "message": "Am I on track for my squat PR?",
            "history": []
        }
    """
    try:
        response_text, updated_history = chat(req.message, req.history)
        return ChatResponse(
            response=response_text,
            history=updated_history
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Run directly ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True   # auto-reloads on file save during development
    )