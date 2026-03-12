import streamlit as st
import requests
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TigerData Fitness Tracker",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_BASE = "http://localhost:8000"
LIFTS    = ["Bench Press", "Squat", "Deadlift"]
TARGETS  = {"Bench Press": 225, "Squat": 315, "Deadlift": 285}
COLORS   = {"Bench Press": "#FF6B6B", "Squat": "#4ECDC4", "Deadlift": "#45B7D1"}

# ── API helpers ───────────────────────────────────────────────────────────────
# All data fetching goes through these functions.
# @st.cache_data caches the result so repeated renders don't re-hit the API.

@st.cache_data(ttl=60)   # cache for 60 seconds
def fetch_trend(lift: str, weeks: int = 12):
    """Fetches weekly 1RM trend from the continuous aggregate via FastAPI."""
    try:
        r = requests.get(
            f"{API_BASE}/trend/{lift}",
            params={"weeks": weeks},
            timeout=10
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        st.error(f"Failed to fetch trend for {lift}: {e}")
        return []

@st.cache_data(ttl=60)
def fetch_projection(lift: str):
    """Fetches PR projection from the linear regression model via FastAPI."""
    try:
        r = requests.get(f"{API_BASE}/projection/{lift}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to fetch projection for {lift}: {e}")
        return {}

@st.cache_data(ttl=60)
def fetch_next_session(lift: str):
    """Fetches next session recommendation via FastAPI."""
    try:
        r = requests.get(f"{API_BASE}/next-session/{lift}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to fetch next session for {lift}: {e}")
        return {}

def post_log(text: str):
    """Posts a natural language workout log to FastAPI."""
    try:
        r = requests.post(
            f"{API_BASE}/log",
            json={"text": text},
            timeout=15
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def post_chat(message: str, history: list):
    """Sends a chat message with conversation history to the agent via FastAPI."""
    try:
        r = requests.post(
            f"{API_BASE}/chat",
            json={"message": message, "history": history},
            timeout=30
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "response": f"Error: {e}", "history": history}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏋️ TigerData Fitness")
    st.caption("Powered by TimescaleDB + Claude")
    st.divider()

    # API health check on every render
    try:
        health = requests.get(f"{API_BASE}/health", timeout=3).json()
        st.success(f"API: {health['status'].upper()}")
    except Exception:
        st.error("API: OFFLINE — start FastAPI first")

    st.divider()

    # Navigation
    page = st.radio(
        "Navigate",
        ["📊 Dashboard", "💪 Next Session", "🤖 AI Coach", "📝 Log Workout"],
        label_visibility="collapsed"
    )

    st.divider()

    # Weeks selector affects trend charts
    weeks = st.slider("Trend window (weeks)", min_value=4, max_value=12, value=8)

    st.divider()
    st.caption("2026 PR Targets")
    for lift, target in TARGETS.items():
        st.caption(f"• {lift}: **{target} lbs**")

# ── Page: Dashboard ───────────────────────────────────────────────────────────
if page == "📊 Dashboard":
    st.title("📊 PR Progress Dashboard")
    st.caption(
        "Weekly best estimated 1RM from the `weekly_1rm` "
        "continuous aggregate — updated automatically as new sets are logged."
    )

    # ── Metric cards row ──────────────────────────────────────────────────────
    cols = st.columns(3)
    for i, lift in enumerate(LIFTS):
        proj = fetch_projection(lift)
        with cols[i]:
            if proj and "error" not in proj:
                current  = proj.get("current_e1rm_lbs", 0)
                target   = proj.get("target_lbs", TARGETS[lift])
                on_track = proj.get("on_track", False)
                pct      = round(current / target * 100, 1)
                delta    = round(current - target, 1)

                st.metric(
                    label=lift,
                    value=f"{current} lbs",
                    delta=f"{delta:+.1f} vs {target} lb target",
                    delta_color="normal"
                )
                st.progress(min(pct / 100, 1.0))
                status = "✅ On Pace" if on_track else "⚠️ Behind Pace"
                st.caption(f"{status} — {pct}% of target")
            else:
                st.metric(label=lift, value="No data")

    st.divider()

    # ── Trend charts ──────────────────────────────────────────────────────────
    st.subheader(f"Weekly Best e1RM — Last {weeks} Weeks")
    st.caption(
        "Data source: `weekly_1rm` continuous aggregate view. "
        "Each point is the best estimated 1RM in that week's chunk, "
        "calculated using the Epley formula: weight × (1 + reps/30)."
    )

    # Combined chart showing all 3 lifts
    fig = go.Figure()
    has_data = False

    for lift in LIFTS:
        trend = fetch_trend(lift, weeks=weeks)
        if not trend:
            continue
        has_data = True

        df = pd.DataFrame(trend)
        # Ensure week column is parsed as datetime for proper x-axis formatting
        df["week"] = pd.to_datetime(df["week"])
        df = df.sort_values("week")

        # Target reference line
        fig.add_hline(
            y=TARGETS[lift],
            line_dash="dot",
            line_color=COLORS[lift],
            opacity=0.4,
            annotation_text=f"{lift} target ({TARGETS[lift]} lbs)",
            annotation_position="right"
        )

        # Trend line
        fig.add_trace(go.Scatter(
            x=df["week"],
            y=df["e1rm_lbs"],
            mode="lines+markers",
            name=lift,
            line=dict(color=COLORS[lift], width=2),
            marker=dict(size=8),
            hovertemplate=(
                f"<b>{lift}</b><br>"
                "Week: %{x|%b %d}<br>"
                "e1RM: %{y:.1f} lbs<br>"
                "<extra></extra>"
            )
        ))

    if has_data:
        fig.update_layout(
            xaxis_title="Week",
            yaxis_title="Estimated 1RM (lbs)",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            height=400,
            margin=dict(t=40, r=120)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No trend data available. Log some workouts first.")

    st.divider()

    # ── Per-lift detail section ───────────────────────────────────────────────
    st.subheader("Per-Lift Breakdown")
    tab1, tab2, tab3 = st.tabs(LIFTS)

    for tab, lift in zip([tab1, tab2, tab3], LIFTS):
        with tab:
            trend = fetch_trend(lift, weeks=weeks)
            proj  = fetch_projection(lift)

            col_left, col_right = st.columns([2, 1])

            with col_left:
                if trend:
                    df = pd.DataFrame(trend)
                    df["week"] = pd.to_datetime(df["week"])
                    df = df.sort_values("week")

                    fig2 = go.Figure()

                    # Epley e1RM bars
                    fig2.add_trace(go.Bar(
                        x=df["week"],
                        y=df["e1rm_lbs"],
                        name="Best e1RM (Epley)",
                        marker_color=COLORS[lift],
                        opacity=0.7,
                        hovertemplate="Week: %{x|%b %d}<br>e1RM: %{y:.1f} lbs<extra></extra>"
                    ))

                    # Top weight lifted (not estimated)
                    if "top_weight_lbs" in df.columns:
                        df["top_weight_lbs"] = df["top_weight_kg"] * 2.205
                        fig2.add_trace(go.Scatter(
                            x=df["week"],
                            y=df["top_weight_lbs"],
                            name="Top Weight Lifted",
                            mode="lines+markers",
                            line=dict(color="white", width=1.5, dash="dash"),
                            hovertemplate="Top weight: %{y:.0f} lbs<extra></extra>"
                        ))

                    # Target line
                    fig2.add_hline(
                        y=TARGETS[lift],
                        line_dash="dot",
                        line_color="yellow",
                        opacity=0.6,
                        annotation_text=f"2026 Target: {TARGETS[lift]} lbs"
                    )

                    fig2.update_layout(
                        height=300,
                        margin=dict(t=20, b=20),
                        legend=dict(orientation="h"),
                        xaxis_title="Week",
                        yaxis_title="lbs"
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info(f"No data for {lift} yet.")

            with col_right:
                if proj and "error" not in proj:
                    st.metric("Current e1RM",     f"{proj.get('current_e1rm_lbs', '—')} lbs")
                    st.metric("Projected (target date)", f"{proj.get('projected_e1rm_lbs', '—')} lbs")
                    st.metric("Weekly gain",       f"{proj.get('weekly_gain_lbs', '—')} lbs/wk")
                    st.metric("Weeks remaining",   proj.get('weeks_remaining', '—'))
                    st.metric("Data points",       f"{proj.get('data_points', '—')} weeks")

                    on_track = proj.get("on_track", False)
                    if on_track:
                        st.success("✅ ON PACE for 2026 target")
                    else:
                        st.warning("⚠️ BEHIND PACE — needs acceleration")

# ── Page: Next Session ────────────────────────────────────────────────────────
elif page == "💪 Next Session":
    st.title("💪 Next Session Planner")
    st.caption(
        "RPE-based double progression. Recommendations are generated "
        "from your last session's weight and RPE stored in the hypertable."
    )

    selected_lift = st.selectbox("Select lift to plan", LIFTS)

    if st.button("Generate Session Plan", type="primary"):
        with st.spinner(f"Querying last {selected_lift} session..."):
            rec = fetch_next_session(selected_lift)

        if rec and "error" not in rec:
            st.success(f"Session plan for **{selected_lift}**")

            # Context from last session
            col1, col2, col3 = st.columns(3)
            col1.metric("Last weight",  f"{rec.get('last_weight_lbs', '—')} lbs")
            col2.metric("Last reps",    rec.get('last_reps', '—'))
            col3.metric("Avg RPE",      rec.get('avg_rpe', '—'))

            st.caption(f"📈 Progression logic: {rec.get('progression_reason', '—')}")
            st.divider()

            # Warmup sets table
            st.subheader("Warmup Sets")
            warmup = rec.get("warmup_sets", [])
            if warmup:
                warmup_df = pd.DataFrame(warmup)
                warmup_df.columns = ["Set", "Weight (lbs)", "Reps", "Type"]
                st.dataframe(warmup_df, use_container_width=True, hide_index=True)

            # Working sets table
            st.subheader("Working Sets")
            working = rec.get("working_sets", [])
            if working:
                working_df = pd.DataFrame(working)
                working_df.columns = ["Set", "Weight (lbs)", "Reps", "Type"]
                st.dataframe(working_df, use_container_width=True, hide_index=True)

                # Visual bar chart of the session
                all_sets = warmup + working
                sets_df = pd.DataFrame(all_sets)
                fig3 = px.bar(
                    sets_df,
                    x="set",
                    y="weight_lbs",
                    color="note",
                    color_discrete_map={"warmup": "#888", "working": COLORS[selected_lift]},
                    labels={"set": "Set Number", "weight_lbs": "Weight (lbs)", "note": "Type"},
                    title=f"{selected_lift} — Full Session Overview"
                )
                fig3.update_layout(height=300, margin=dict(t=40))
                st.plotly_chart(fig3, use_container_width=True)
        else:
            st.error(rec.get("error", "Could not generate session plan."))

# ── Page: AI Coach ────────────────────────────────────────────────────────────
elif page == "🤖 AI Coach":
    st.title("🤖 AI Fitness Coach")
    st.caption(
        "Powered by Claude + TimescaleDB. Ask about your progress, "
        "log workouts, or get session recommendations."
    )

    # Initialize session state for conversation history
    # Streamlit re-runs the entire script on every interaction,
    # so session_state is how we persist data between runs.
    if "chat_history" not in st.session_state:
        st.session_state.chat_history   = []
        st.session_state.display_messages = []

    # Render existing conversation
    for msg in st.session_state.display_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input at the bottom
    if prompt := st.chat_input("Ask your coach anything..."):
        # Show user message immediately
        st.session_state.display_messages.append({
            "role": "user",
            "content": prompt
        })
        with st.chat_message("user"):
            st.markdown(prompt)

        # Call FastAPI chat endpoint with full history
        with st.chat_message("assistant"):
            with st.spinner("Coach is thinking..."):
                result = post_chat(
                    message=prompt,
                    history=st.session_state.chat_history
                )

            if "error" in result and "response" not in result:
                response_text = f"Error: {result['error']}"
            else:
                response_text = result.get("response", "No response received.")
                # Update conversation history for next turn
                st.session_state.chat_history = result.get(
                    "history",
                    st.session_state.chat_history
                )

            st.markdown(response_text)
            st.session_state.display_messages.append({
                "role": "assistant",
                "content": response_text
            })

    # Clear conversation button
    if st.session_state.display_messages:
        if st.button("Clear conversation"):
            st.session_state.chat_history     = []
            st.session_state.display_messages = []
            st.rerun()

# ── Page: Log Workout ─────────────────────────────────────────────────────────
elif page == "📝 Log Workout":
    st.title("📝 Log a Workout")
    st.caption(
        "Describe your session in plain English. The NL parser will extract "
        "sets and insert them into the `workout_sets` hypertable."
    )

    st.subheader("Natural Language Log")

    # Example prompts to guide the user
    st.info(
        "**Examples:**\n"
        "- *Benched 185 for 3 sets of 5 at RPE 8*\n"
        "- *Squatted 225x3x5, last set RPE 8.5*\n"
        "- *Hit a deadlift PR — 275 for a single at RPE 9*"
    )

    workout_text = st.text_area(
        "Describe your workout",
        placeholder="e.g. Squatted 225 for 3 sets of 5 at RPE 8",
        height=100
    )

    if st.button("Log Workout", type="primary", disabled=not workout_text.strip()):
        with st.spinner("Parsing and logging..."):
            result = post_log(workout_text.strip())

        if "error" in result:
            st.error(f"Failed to log: {result['error']}")
        else:
            st.success(result.get("message", "Workout logged successfully!"))
            st.caption(
                "✅ Sets inserted into `workout_sets` hypertable. "
                "The `weekly_1rm` continuous aggregate will reflect "
                "this data on its next scheduled refresh."
            )
            # Clear the cache so Dashboard shows fresh data
            fetch_trend.clear()
            fetch_projection.clear()