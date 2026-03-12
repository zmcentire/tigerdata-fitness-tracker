import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from dotenv import load_dotenv
import anthropic
from loaders.nl_parser import log_workout_from_text
from agents.pr_projector import (
    project_1rm,
    project_all_lifts,
    get_next_session,
    print_projection_report
)

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── Tool definitions ────────────────────────────────────────────────────────
# These are the functions Claude can call during a conversation.
# Each tool maps to a real Python function that queries TigerData.

TOOLS = [
    {
        "name": "log_workout",
        "description": (
            "Log a workout session from natural language input. "
            "Use this when the user describes sets they just completed. "
            "Examples: 'I just benched 185 for 3x5 at RPE 8', "
            "'Hit a new squat PR — 275lbs for a single', "
            "'Deadlifted 225 for 4 sets of 3 tonight'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_text": {
                    "type": "string",
                    "description": "The natural language description of the workout"
                }
            },
            "required": ["workout_text"]
        }
    },
    {
        "name": "get_pr_projection",
        "description": (
            "Get the current estimated 1RM and end-of-month PR projection "
            "for one or all compound lifts. Use this when the user asks: "
            "'am I on track for my PR?', 'how's my bench progressing?', "
            "'will I hit my squat goal?', or requests a progress report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lift": {
                    "type": "string",
                    "description": (
                        "The lift to project. One of: "
                        "'Bench Press', 'Squat', 'Deadlift', or 'all'"
                    ),
                    "enum": ["Bench Press", "Squat", "Deadlift", "all"]
                }
            },
            "required": ["lift"]
        }
    },
    {
        "name": "get_next_session",
        "description": (
            "Get the recommended working sets for the next session of a "
            "specific lift, based on the last session's performance and RPE. "
            "Use this when the user asks: 'what should I lift tomorrow?', "
            "'plan my bench session', 'what weight for squats next time?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lift": {
                    "type": "string",
                    "description": "The lift to plan. One of: 'Bench Press', 'Squat', 'Deadlift'",
                    "enum": ["Bench Press", "Squat", "Deadlift"]
                }
            },
            "required": ["lift"]
        }
    },
    {
        "name": "get_full_report",
        "description": (
            "Generate a complete training report covering all three lifts: "
            "current 1RM estimates, PR projections, and next session plans. "
            "Use this when the user asks for a full overview, weekly summary, "
            "or comprehensive progress check."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

# ── Tool execution ──────────────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Routes tool calls from Claude to the appropriate Python function.
    Returns a string that gets sent back to Claude as the tool result.
    """
    try:
        if tool_name == "log_workout":
            text = tool_input["workout_text"]
            log_workout_from_text(text)
            return (
                f"Successfully logged workout: '{text}'. "
                f"Sets have been inserted into the workout_sets hypertable "
                f"and the weekly_1rm continuous aggregate will reflect this "
                f"at the next refresh."
            )

        elif tool_name == "get_pr_projection":
            lift = tool_input["lift"]
            if lift == "all":
                results = project_all_lifts()
                # Format as readable JSON for Claude to interpret
                summary = {}
                for name, proj in results.items():
                    if "error" not in proj:
                        summary[name] = {
                            "current_e1rm_lbs":    proj["current_e1rm_lbs"],
                            "projected_e1rm_lbs":  proj["projected_e1rm_lbs"],
                            "target_lbs":          proj["target_lbs"],
                            "on_track":            proj["on_track"],
                            "weekly_gain_lbs":     proj["weekly_gain_lbs"],
                            "weeks_remaining":     proj["weeks_remaining"],
                            "data_points":         proj["data_points"]
                        }
                    else:
                        summary[name] = proj
                return json.dumps(summary, indent=2)
            else:
                proj = project_1rm(lift)
                if "error" in proj:
                    return f"Error getting projection for {lift}: {proj['error']}"
                return json.dumps({
                    "exercise":            lift,
                    "current_e1rm_lbs":   proj["current_e1rm_lbs"],
                    "projected_e1rm_lbs": proj["projected_e1rm_lbs"],
                    "target_lbs":         proj["target_lbs"],
                    "on_track":           proj["on_track"],
                    "weekly_gain_lbs":    proj["weekly_gain_lbs"],
                    "weeks_remaining":    proj["weeks_remaining"],
                    "data_points":        proj["data_points"]
                }, indent=2)

        elif tool_name == "get_next_session":
            lift = tool_input["lift"]
            rec = get_next_session(lift)
            if "error" in rec:
                return f"Error: {rec['error']}"
            return json.dumps({
                "exercise":           lift,
                "last_session_date":  str(rec["last_session"]),
                "last_weight_lbs":    rec["last_weight_lbs"],
                "last_reps":          rec["last_reps"],
                "avg_rpe":            rec["avg_rpe"],
                "progression_reason": rec["progression_reason"],
                "warmup_sets":        rec["warmup_sets"],
                "working_sets":       rec["working_sets"]
            }, indent=2)

        elif tool_name == "get_full_report":
            projections = project_all_lifts()
            report = {"projections": {}, "next_sessions": {}}

            for lift in ["Bench Press", "Squat", "Deadlift"]:
                proj = projections.get(lift, {})
                if "error" not in proj:
                    report["projections"][lift] = {
                        "current_e1rm_lbs":   proj["current_e1rm_lbs"],
                        "projected_e1rm_lbs": proj["projected_e1rm_lbs"],
                        "target_lbs":         proj["target_lbs"],
                        "on_track":           proj["on_track"],
                        "weekly_gain_lbs":    proj["weekly_gain_lbs"]
                    }
                rec = get_next_session(lift)
                if "error" not in rec:
                    report["next_sessions"][lift] = {
                        "next_weight_lbs": rec["next_weight_lbs"],
                        "next_reps":       rec["next_reps"],
                        "reason":          rec["progression_reason"],
                        "working_sets":    rec["working_sets"]
                    }

            return json.dumps(report, indent=2)

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Tool execution error in {tool_name}: {str(e)}"

# ── Agent conversation loop ─────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert powerlifting coach AND a certified gym bro philosopher
with direct access to the athlete's TigerData (TimescaleDB) training database.

Your athlete's 2026 PR targets are:
- Bench Press: 225 lbs
- Squat: 315 lbs
- Deadlift: 285 lbs

Personality: you are data-driven and technically sharp when it comes to lifting —
you always pull real numbers from the database when discussing PRs and progress.
But you also have the energy of someone who has spent way too much time in the gym
and developed strong opinions about life as a result. You can riff on:
- Dudebro life philosophy ("the bar doesn't care about your feelings, bro")
- Gym etiquette hot takes
- Motivational speeches that get increasingly unhinged
- Answering completely unrelated life questions through a lifting metaphor
- Existential questions about gains, legacy, and what it all means

SPECIALIST DIMENSIONS:

1. ANIME ENCYCLOPEDIA
You have deep, encyclopedic knowledge of anime across the board — Dragon Ball Z,
One Piece, Jujutsu Kaisen, Naruto, Attack on Titan, Hunter x Hunter, and beyond.
You treat DBZ with particular reverence but you are well-rounded. You have strong
opinions on power scaling, story arcs, and the greatest anime debates of our time.
You explain lifting concepts through anime/DBZ power scaling and reference anime SPARINGLY 
and only when it genuinely fits — you are not constantly making anime comparisons, 
but when the moment is right, you commit fully.A well-placed "that's giving Gear 5 Luffy energy" 
once in a while lands better thanforcing it into every response. 
When anime does come up organically, your knowledge is specific and your takes are confident. 
You will not be argued out of your positions.

2. CONNOISSEUR OF SINGLE MOMS
For reasons you have never fully examined but have fully accepted, you are uniquely,
specifically, and devotedly attracted to single moms. You give advice on this topic
with the confidence of someone who has done extensive field research. Your tips are
wholesome but slightly unhinged — you believe the key is showing up, being reliable,
and always complimenting the kids' drawings. You treat this subject with the same
analytical depth you bring to programming. You have theories. They are detailed.

3. CERTIFIED DOG PETTING EXPERT
You have a deep, almost spiritual relationship with dogs and have developed strong
opinions on the craft of petting them. You distinguish between the casual pet, the
respectful meet-and-greet scritch, the full-commitment ear rub, and the sacred
belly rub (only offered, never demanded). You believe most people are petting dogs
wrong and you are not afraid to say so. You can assess a dog's preferred petting
zone from across the room.

RULES:
- When asked about training data, always use the database tools. Be accurate.
- When asked about life, anime, single moms, or dogs, lean in fully.
- Connect all four domains when the opportunity arises.
  ("Training legs is like being a single dad at the park — nobody wants to do it
  but the ones who show up consistently are the most attractive people in the world.")
- You never refer to yourself by any name. You are simply the coach.
- You never break character. Every problem in life can be solved by either:
  (a) checking the data, or (b) adding more weight to the bar."""

def chat(user_message: str, conversation_history: list) -> tuple[str, list]:
    """
    Sends a message to the agent and handles any tool calls.
    Returns the agent's final response and updated conversation history.

    Handles multi-turn tool use: Claude may call multiple tools before
    giving a final response. This loop processes each tool call in sequence.
    """
    # Add user message to history
    conversation_history.append({
        "role": "user",
        "content": user_message
    })

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history
        )

        # If Claude is done (no more tool calls), return the text response
        if response.stop_reason == "end_turn":
            assistant_text = response.content[0].text
            conversation_history.append({
                "role": "assistant",
                "content": assistant_text
            })
            return assistant_text, conversation_history

        # If Claude wants to use a tool, execute it and feed result back
        if response.stop_reason == "tool_use":
            # Add Claude's response (including tool_use blocks) to history
            conversation_history.append({
                "role": "assistant",
                "content": response.content
            })

            # Process each tool call in the response
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [Agent calling tool: {block.name}]")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result
                    })

            # Add tool results to history and loop back for Claude's next response
            conversation_history.append({
                "role":    "user",
                "content": tool_results
            })
            # Loop continues — Claude will now respond to the tool results

# ── Main interactive loop ───────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  TIGERDATA FITNESS COACH")
    print("  Powered by Claude + TimescaleDB")
    print("="*60)
    print("\nCommands:")
    print("  Type your message to chat with your coach")
    print("  Type 'quit' or 'exit' to end the session")
    print("  Type 'clear' to reset conversation history")
    print("\nExample prompts:")
    print("  'I just benched 185 for 3 sets of 5 at RPE 8'")
    print("  'Am I on track for my squat PR?'")
    print("  'Plan my deadlift session for tomorrow'")
    print("  'Give me a full training report'")
    print("="*60 + "\n")

    conversation_history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if not user_input:
            continue

        if user_input.lower() in ["quit", "exit"]:
            print("Session ended. Keep lifting.")
            break

        if user_input.lower() == "clear":
            conversation_history = []
            print("Conversation history cleared.\n")
            continue

        print("\nCoach: ", end="", flush=True)
        response, conversation_history = chat(user_input, conversation_history)
        print(response)
        print()

if __name__ == "__main__":
    main()