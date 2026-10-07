"""Core nutrition math: BMR, TDEE, and calorie/macro targets with safety limits.

Everything here is a pure function (no database, no network) so it is easy to
test. All units are metric: kilograms, centimetres, kilocalories (kcal).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Energy content of 1 kg of body-weight change. The classic "3500 kcal per
# pound" rule converted to metric. It's an approximation (real tissue is a mix
# of fat, water and lean mass) but it is the standard planning number.
KCAL_PER_KG = 7700

# Multipliers applied to BMR to estimate total daily energy expenditure.
ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary": 1.2,  # desk job, little exercise
    "light": 1.375,  # light exercise 1-3 days/week
    "moderate": 1.55,  # moderate exercise 3-5 days/week
    "active": 1.725,  # hard exercise 6-7 days/week
    "very_active": 1.9,  # physical job + hard training
}

# Safety limits.
MAX_LOSS_PCT_PER_WEEK = 1.0  # never plan to lose more than 1% of body weight/week
MAX_GAIN_PCT_PER_WEEK = 0.5  # gaining faster than this is mostly fat
DEFAULT_RATE_PCT = {"cut": 0.5, "maintain": 0.0, "bulk": 0.25}
CALORIE_FLOOR = {"male": 1500, "female": 1200}

# Macro rules (grams per kg of body weight / share of calories).
PROTEIN_G_PER_KG = {"cut": 2.2, "maintain": 1.8, "bulk": 1.8}
FAT_SHARE = 0.25  # 25% of calories from fat
FAT_MIN_G_PER_KG = 0.6  # hormonal-health minimum
KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9}

GOALS = ("cut", "maintain", "bulk")
SEXES = ("male", "female")


def bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Basal metabolic rate (kcal/day) using the Mifflin-St Jeor equation.

    BMR = 10*weight(kg) + 6.25*height(cm) - 5*age(y) + s
    where s = +5 for males and -161 for females.
    """
    if weight_kg <= 0 or height_cm <= 0 or age <= 0:
        raise ValueError("weight, height and age must be positive")
    if sex not in SEXES:
        raise ValueError(f"sex must be one of {SEXES}")
    s = 5 if sex == "male" else -161
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + s


def tdee_from_activity(bmr: float, activity_level: str) -> float:
    """Total daily energy expenditure = BMR x activity multiplier."""
    if activity_level not in ACTIVITY_MULTIPLIERS:
        raise ValueError(f"activity_level must be one of {list(ACTIVITY_MULTIPLIERS)}")
    return bmr * ACTIVITY_MULTIPLIERS[activity_level]


@dataclass
class Targets:
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    tdee: int
    goal: str
    weekly_rate_pct: float  # signed: negative = losing
    expected_weekly_change_kg: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def calorie_target(
    tdee: float,
    weight_kg: float,
    sex: str,
    goal: str,
    rate_pct: float | None = None,
) -> tuple[float, float, list[str]]:
    """Return (calories, actual weekly rate % [signed], warnings).

    `rate_pct` is the *unsigned* percentage of body weight to lose (cut) or
    gain (bulk) per week. It is capped at safe limits, and the result is
    never allowed below the calorie floor for the user's sex.
    """
    if goal not in GOALS:
        raise ValueError(f"goal must be one of {GOALS}")
    warnings: list[str] = []
    if goal == "maintain":
        return tdee, 0.0, warnings

    rate = DEFAULT_RATE_PCT[goal] if rate_pct is None else abs(rate_pct)
    cap = MAX_LOSS_PCT_PER_WEEK if goal == "cut" else MAX_GAIN_PCT_PER_WEEK
    if rate > cap:
        warnings.append(
            f"Requested {rate:.2f}%/week is above the safe limit; capped at {cap:.2f}%/week."
        )
        rate = cap

    kg_per_week = weight_kg * rate / 100
    daily_delta = kg_per_week * KCAL_PER_KG / 7
    sign = -1 if goal == "cut" else 1
    calories = tdee + sign * daily_delta

    floor = CALORIE_FLOOR[sex]
    if calories < floor:
        warnings.append(
            f"Target raised to the {floor} kcal minimum; you'll lose weight more slowly than requested."
        )
        calories = floor
        # Recalculate the real rate that the floor allows.
        daily_delta = max(tdee - calories, 0)
        rate = daily_delta * 7 / KCAL_PER_KG / weight_kg * 100
        if tdee <= floor:
            warnings.append(
                "Your estimated maintenance is at or below the calorie floor; consider "
                "increasing activity rather than eating less."
            )

    return calories, sign * rate, warnings


def macro_split(calories: float, weight_kg: float, goal: str) -> tuple[int, int, int, list[str]]:
    """Split calories into (protein_g, carbs_g, fat_g, warnings).

    1. Protein is set per kg of body weight (higher on a cut to protect muscle).
    2. Fat is 25% of calories, but never below 0.6 g/kg.
    3. Carbs fill whatever calories remain.
    """
    warnings: list[str] = []
    protein = PROTEIN_G_PER_KG[goal] * weight_kg
    fat = max(calories * FAT_SHARE / KCAL_PER_G["fat"], FAT_MIN_G_PER_KG * weight_kg)
    remaining = calories - protein * KCAL_PER_G["protein"] - fat * KCAL_PER_G["fat"]
    if remaining < 0:
        warnings.append("Calories are too low to fit protein and fat minimums; carbs set to 0.")
        remaining = 0
    carbs = remaining / KCAL_PER_G["carbs"]
    return round(protein), round(carbs), round(fat), warnings


def compute_targets(
    tdee: float,
    weight_kg: float,
    sex: str,
    goal: str,
    rate_pct: float | None = None,
) -> Targets:
    """Full target calculation from a TDEE (formula-based or adaptive)."""
    calories, rate, warnings = calorie_target(tdee, weight_kg, sex, goal, rate_pct)
    protein, carbs, fat, macro_warnings = macro_split(calories, weight_kg, goal)
    weekly_change = weight_kg * rate / 100
    return Targets(
        calories=round(calories),
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        tdee=round(tdee),
        goal=goal,
        weekly_rate_pct=round(rate, 3),
        expected_weekly_change_kg=round(weekly_change, 3),
        warnings=warnings + macro_warnings,
    )
