"""Rule-based weekly workout planner.

Inputs: goal (cut / maintain / bulk), training days per week (2-6), and the
equipment available. Output: a weekly plan of named sessions, each a list of
exercises with sets, reps and rest.

The planner is deterministic (same inputs -> same plan) so it is testable.
"""

from __future__ import annotations

EQUIPMENT = ("full_gym", "dumbbells", "bodyweight")

# Exercise library: movement pattern -> best option for each equipment level.
LIBRARY: dict[str, dict[str, str]] = {
    "squat": {"full_gym": "Barbell back squat", "dumbbells": "Goblet squat", "bodyweight": "Bodyweight squat"},
    "hinge": {"full_gym": "Romanian deadlift", "dumbbells": "Dumbbell Romanian deadlift", "bodyweight": "Single-leg hip hinge"},
    "lunge": {"full_gym": "Walking lunge", "dumbbells": "Dumbbell split squat", "bodyweight": "Reverse lunge"},
    "horizontal_push": {"full_gym": "Barbell bench press", "dumbbells": "Dumbbell bench press", "bodyweight": "Push-up"},
    "vertical_push": {"full_gym": "Overhead press", "dumbbells": "Seated dumbbell shoulder press", "bodyweight": "Pike push-up"},
    "horizontal_pull": {"full_gym": "Seated cable row", "dumbbells": "One-arm dumbbell row", "bodyweight": "Inverted row (table)"},
    "vertical_pull": {"full_gym": "Lat pulldown", "dumbbells": "Dumbbell pullover", "bodyweight": "Pull-up or doorway row"},
    "glute": {"full_gym": "Hip thrust", "dumbbells": "Dumbbell hip thrust", "bodyweight": "Glute bridge"},
    "calves": {"full_gym": "Standing calf raise", "dumbbells": "Dumbbell calf raise", "bodyweight": "Single-leg calf raise"},
    "biceps": {"full_gym": "Cable curl", "dumbbells": "Dumbbell curl", "bodyweight": "Towel curl isometric"},
    "triceps": {"full_gym": "Cable triceps pushdown", "dumbbells": "Overhead dumbbell extension", "bodyweight": "Bench dip"},
    "core": {"full_gym": "Cable crunch", "dumbbells": "Dumbbell side bend", "bodyweight": "Plank"},
}

# Session templates: name -> movement patterns, in order (big lifts first).
SESSIONS: dict[str, list[str]] = {
    "Full Body A": ["squat", "horizontal_push", "horizontal_pull", "hinge", "core"],
    "Full Body B": ["hinge", "vertical_push", "vertical_pull", "lunge", "calves"],
    "Full Body C": ["lunge", "horizontal_push", "vertical_pull", "glute", "core"],
    "Upper A": ["horizontal_push", "horizontal_pull", "vertical_push", "vertical_pull", "triceps", "biceps"],
    "Upper B": ["vertical_push", "vertical_pull", "horizontal_push", "horizontal_pull", "biceps", "triceps"],
    "Lower A": ["squat", "hinge", "lunge", "calves", "core"],
    "Lower B": ["hinge", "squat", "glute", "calves", "core"],
    "Push": ["horizontal_push", "vertical_push", "triceps", "core"],
    "Pull": ["vertical_pull", "horizontal_pull", "biceps", "core"],
    "Legs": ["squat", "hinge", "lunge", "glute", "calves"],
}

# Split by days per week.
SPLITS: dict[int, tuple[str, list[str]]] = {
    2: ("Full body", ["Full Body A", "Full Body B"]),
    3: ("Full body", ["Full Body A", "Full Body B", "Full Body C"]),
    4: ("Upper / lower", ["Upper A", "Lower A", "Upper B", "Lower B"]),
    5: ("Upper / lower + push / pull / legs", ["Upper A", "Lower A", "Push", "Pull", "Legs"]),
    6: ("Push / pull / legs x2", ["Push", "Pull", "Legs", "Push", "Pull", "Legs"]),
}

# Weekday layout that spreads sessions out (index 0 = Monday).
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_LAYOUT: dict[int, list[int]] = {
    2: [0, 3],
    3: [0, 2, 4],
    4: [0, 1, 3, 4],
    5: [0, 1, 2, 4, 5],
    6: [0, 1, 2, 3, 4, 5],
}

# Set/rep scheme by goal: (sets for main lifts, reps for main, reps for accessories, rest seconds).
SCHEMES = {
    "cut": {"main_sets": 3, "main_reps": "6-8", "acc_sets": 2, "acc_reps": "10-15", "rest_s": 120},
    "maintain": {"main_sets": 3, "main_reps": "6-10", "acc_sets": 3, "acc_reps": "10-12", "rest_s": 120},
    "bulk": {"main_sets": 4, "main_reps": "6-10", "acc_sets": 3, "acc_reps": "8-12", "rest_s": 150},
}
MAIN_PATTERNS = {"squat", "hinge", "horizontal_push", "vertical_push", "horizontal_pull", "vertical_pull"}

CARDIO = {
    "cut": "20-30 min brisk walk or easy cycling (zone 2), plus 8-10k steps daily",
    "maintain": "20 min zone 2 cardio twice a week",
    "bulk": "Optional: 15-20 min easy cardio for heart health",
}


def build_exercise(pattern: str, equipment: str, goal: str, position: int) -> dict:
    scheme = SCHEMES[goal]
    # The first two movements of a session are "main" lifts if they are compound.
    is_main = pattern in MAIN_PATTERNS and position < 2
    return {
        "pattern": pattern,
        "name": LIBRARY[pattern][equipment],
        "sets": scheme["main_sets"] if is_main else scheme["acc_sets"],
        "reps": scheme["main_reps"] if is_main else scheme["acc_reps"],
        "rest_seconds": scheme["rest_s"] if is_main else 90,
    }


def plan_week(goal: str, days_per_week: int, equipment: str) -> dict:
    """Return a full weekly plan as a JSON-friendly dict."""
    if goal not in SCHEMES:
        raise ValueError(f"goal must be one of {list(SCHEMES)}")
    if days_per_week not in SPLITS:
        raise ValueError("days_per_week must be between 2 and 6")
    if equipment not in EQUIPMENT:
        raise ValueError(f"equipment must be one of {EQUIPMENT}")

    split_name, session_names = SPLITS[days_per_week]
    training_days = DAY_LAYOUT[days_per_week]
    week = []
    session_iter = iter(session_names)
    for i, day in enumerate(DAY_NAMES):
        if i in training_days:
            name = next(session_iter)
            exercises = [build_exercise(p, equipment, goal, pos) for pos, p in enumerate(SESSIONS[name])]
            week.append({"day": day, "session": name, "exercises": exercises})
        else:
            week.append({"day": day, "session": "Rest", "exercises": [], "note": CARDIO[goal]})

    notes = [
        "Progressive overload: when you hit the top of the rep range on all sets, add weight (or reps for bodyweight).",
        "Leave 1-3 reps in reserve on most sets.",
    ]
    if goal == "cut":
        notes.append("Keep lifting heavy on a cut; it tells your body to keep muscle.")
    if equipment == "bodyweight":
        notes.append("Make bodyweight moves harder with slower tempo, pauses, or single-limb versions.")

    return {
        "goal": goal,
        "days_per_week": days_per_week,
        "equipment": equipment,
        "split": split_name,
        "week": week,
        "cardio": CARDIO[goal],
        "notes": notes,
    }
