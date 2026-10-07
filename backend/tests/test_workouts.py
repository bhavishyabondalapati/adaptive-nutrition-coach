from collections import Counter

import pytest

from app.workouts import EQUIPMENT, LIBRARY, SCHEMES, plan_week


@pytest.mark.parametrize("days", [2, 3, 4, 5, 6])
def test_number_of_training_days(days):
    plan = plan_week("maintain", days, "full_gym")
    training = [d for d in plan["week"] if d["session"] != "Rest"]
    assert len(plan["week"]) == 7
    assert len(training) == days


@pytest.mark.parametrize("days", [2, 3, 4, 5, 6])
def test_every_major_pattern_trained_each_week(days):
    plan = plan_week("bulk", days, "dumbbells")
    patterns = {ex["pattern"] for d in plan["week"] for ex in d["exercises"]}
    for p in ("squat", "hinge", "horizontal_push", "vertical_pull"):
        assert p in patterns


def test_no_more_than_two_training_days_in_a_row_for_three_day_plan():
    plan = plan_week("cut", 3, "bodyweight")
    flags = [d["session"] != "Rest" for d in plan["week"]]
    assert flags == [True, False, True, False, True, False, False]


@pytest.mark.parametrize("equipment", EQUIPMENT)
def test_exercises_match_equipment(equipment):
    plan = plan_week("maintain", 4, equipment)
    allowed = {LIBRARY[p][equipment] for p in LIBRARY}
    for day in plan["week"]:
        for ex in day["exercises"]:
            assert ex["name"] in allowed


def test_bulk_has_more_main_sets_than_cut():
    bulk = plan_week("bulk", 3, "full_gym")["week"][0]["exercises"][0]
    cut = plan_week("cut", 3, "full_gym")["week"][0]["exercises"][0]
    assert bulk["sets"] == SCHEMES["bulk"]["main_sets"] > cut["sets"]


def test_rest_days_have_cardio_note():
    plan = plan_week("cut", 4, "full_gym")
    rest = [d for d in plan["week"] if d["session"] == "Rest"]
    assert rest and all("walk" in d["note"] for d in rest)


def test_six_day_ppl_repeats_twice():
    plan = plan_week("bulk", 6, "full_gym")
    counts = Counter(d["session"] for d in plan["week"])
    assert counts["Push"] == counts["Pull"] == counts["Legs"] == 2


def test_deterministic():
    assert plan_week("cut", 5, "dumbbells") == plan_week("cut", 5, "dumbbells")


@pytest.mark.parametrize(
    "args", [("shred", 3, "full_gym"), ("cut", 1, "full_gym"), ("cut", 7, "full_gym"), ("cut", 3, "kettlebell")]
)
def test_invalid_inputs(args):
    with pytest.raises(ValueError):
        plan_week(*args)
