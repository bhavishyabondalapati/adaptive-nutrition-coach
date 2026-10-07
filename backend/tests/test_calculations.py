import pytest

from app.calculations import (
    ACTIVITY_MULTIPLIERS,
    CALORIE_FLOOR,
    KCAL_PER_KG,
    bmr_mifflin_st_jeor,
    calorie_target,
    compute_targets,
    macro_split,
    tdee_from_activity,
)


# ---------- BMR ----------

def test_bmr_male_matches_hand_calculation():
    # 10*80 + 6.25*180 - 5*30 + 5 = 800 + 1125 - 150 + 5
    assert bmr_mifflin_st_jeor(80, 180, 30, "male") == pytest.approx(1780)


def test_bmr_female_matches_hand_calculation():
    # 10*60 + 6.25*165 - 5*25 - 161 = 600 + 1031.25 - 125 - 161
    assert bmr_mifflin_st_jeor(60, 165, 25, "female") == pytest.approx(1345.25)


def test_bmr_sex_constant_differs_by_166():
    m = bmr_mifflin_st_jeor(70, 175, 40, "male")
    f = bmr_mifflin_st_jeor(70, 175, 40, "female")
    assert m - f == pytest.approx(166)


@pytest.mark.parametrize(
    "delta, expected",
    [({"weight_kg": 1}, 10), ({"height_cm": 1}, 6.25), ({"age": 1}, -5)],
)
def test_bmr_coefficients(delta, expected):
    base = dict(weight_kg=70, height_cm=175, age=30, sex="male")
    bumped = {**base, **{k: base[k] + v for k, v in delta.items()}}
    assert bmr_mifflin_st_jeor(**bumped) - bmr_mifflin_st_jeor(**base) == pytest.approx(expected)


@pytest.mark.parametrize(
    "args",
    [(0, 180, 30, "male"), (80, -1, 30, "male"), (80, 180, 0, "male"), (80, 180, 30, "other")],
)
def test_bmr_rejects_bad_input(args):
    with pytest.raises(ValueError):
        bmr_mifflin_st_jeor(*args)


# ---------- TDEE ----------

@pytest.mark.parametrize("level, mult", list(ACTIVITY_MULTIPLIERS.items()))
def test_tdee_multipliers(level, mult):
    assert tdee_from_activity(1800, level) == pytest.approx(1800 * mult)


def test_tdee_multipliers_increase_with_activity():
    values = list(ACTIVITY_MULTIPLIERS.values())
    assert values == sorted(values)


def test_tdee_rejects_unknown_level():
    with pytest.raises(ValueError):
        tdee_from_activity(1800, "couch")


# ---------- calorie targets ----------

def test_maintain_equals_tdee():
    cal, rate, warnings = calorie_target(2500, 80, "male", "maintain")
    assert cal == 2500 and rate == 0 and warnings == []


def test_cut_default_rate_half_percent():
    # 0.5% of 80 kg = 0.4 kg/week -> 0.4*7700/7 = 440 kcal/day deficit
    cal, rate, warnings = calorie_target(2500, 80, "male", "cut")
    assert cal == pytest.approx(2500 - 440)
    assert rate == pytest.approx(-0.5)
    assert warnings == []


def test_bulk_default_rate_quarter_percent():
    # 0.25% of 80 kg = 0.2 kg/week -> 220 kcal/day surplus
    cal, rate, _ = calorie_target(2500, 80, "male", "bulk")
    assert cal == pytest.approx(2720)
    assert rate == pytest.approx(0.25)


def test_cut_rate_is_capped_at_one_percent():
    cal, rate, warnings = calorie_target(3000, 80, "male", "cut", rate_pct=2.0)
    assert rate == pytest.approx(-1.0)
    assert cal == pytest.approx(3000 - 0.8 * KCAL_PER_KG / 7)
    assert any("capped" in w for w in warnings)


def test_bulk_rate_is_capped_at_half_percent():
    _, rate, warnings = calorie_target(2500, 80, "male", "bulk", rate_pct=1.5)
    assert rate == pytest.approx(0.5)
    assert any("capped" in w for w in warnings)


def test_negative_rate_input_treated_as_magnitude():
    a = calorie_target(2500, 80, "male", "cut", rate_pct=-0.5)
    b = calorie_target(2500, 80, "male", "cut", rate_pct=0.5)
    assert a == b


@pytest.mark.parametrize("sex", ["male", "female"])
def test_calorie_floor_enforced(sex):
    floor = CALORIE_FLOOR[sex]
    cal, rate, warnings = calorie_target(floor + 100, 90, sex, "cut", rate_pct=1.0)
    assert cal == floor
    # The real rate is recomputed from the 100 kcal deficit the floor allows.
    assert rate == pytest.approx(-(100 * 7 / KCAL_PER_KG / 90 * 100))
    assert any("minimum" in w for w in warnings)


def test_floor_above_tdee_gives_extra_warning_and_zero_rate():
    cal, rate, warnings = calorie_target(1100, 50, "female", "cut")
    assert cal == CALORIE_FLOOR["female"]
    assert rate == 0
    assert len(warnings) == 2


def test_invalid_goal():
    with pytest.raises(ValueError):
        calorie_target(2500, 80, "male", "shred")


# ---------- macros ----------

def test_macro_split_cut():
    protein, carbs, fat, warnings = macro_split(2000, 80, "cut")
    assert protein == 176  # 2.2 g/kg
    assert fat == round(2000 * 0.25 / 9)  # 56 g
    expected_carbs = (2000 - 176 * 4 - (2000 * 0.25 / 9) * 9) / 4
    assert carbs == round(expected_carbs)
    assert warnings == []


def test_macro_calories_add_up():
    protein, carbs, fat, _ = macro_split(2600, 75, "bulk")
    total = protein * 4 + carbs * 4 + fat * 9
    assert total == pytest.approx(2600, abs=10)  # rounding slack


def test_fat_minimum_per_kg():
    # Heavy person, low calories: 25% of 1500 = 41.7 g < 0.6*120 = 72 g
    _, _, fat, _ = macro_split(1500, 120, "maintain")
    assert fat == 72


def test_macros_carbs_zero_when_calories_too_low():
    _, carbs, _, warnings = macro_split(900, 120, "cut")
    assert carbs == 0
    assert warnings


# ---------- full pipeline ----------

def test_compute_targets_end_to_end():
    bmr = bmr_mifflin_st_jeor(80, 180, 30, "male")  # 1780
    tdee = tdee_from_activity(bmr, "moderate")  # 2759
    t = compute_targets(tdee, 80, "male", "cut")
    assert t.tdee == 2759
    assert t.calories == round(2759 - 440)
    assert t.expected_weekly_change_kg == pytest.approx(-0.4)
    assert t.protein_g == 176
    assert t.warnings == []
