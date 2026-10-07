from datetime import date, timedelta

import pytest

from app.adaptive import (
    EWMA_ALPHA,
    MAX_WEEKLY_CHANGE,
    estimate_adaptive_tdee,
    ewma_trend,
    linear_slope,
)
from app.calculations import KCAL_PER_KG

END = date(2026, 3, 31)


def days_back(n):
    """Dates for the last n days ending at END (oldest first)."""
    return [END - timedelta(days=n - 1 - i) for i in range(n)]


def simulate(true_tdee, intake, days=28, start_kg=80.0, noise=None):
    """Make weigh-ins that follow energy balance exactly for a known TDEE."""
    weights, kg = [], start_kg
    for i, d in enumerate(days_back(days)):
        weights.append((d, kg + (noise[i % len(noise)] if noise else 0)))
        kg += (intake - true_tdee) / KCAL_PER_KG
    intakes = {d: intake for d in days_back(days)}
    return weights, intakes


# ---------- EWMA ----------

def test_ewma_first_point_starts_trend():
    assert ewma_trend([(END, 80.0)]) == [(END, 80.0)]


def test_ewma_empty():
    assert ewma_trend([]) == []


def test_ewma_single_step():
    d1, d2 = END - timedelta(days=1), END
    trend = ewma_trend([(d1, 80.0), (d2, 81.0)])
    assert trend[-1][1] == pytest.approx(80 + EWMA_ALPHA * 1.0)


def test_ewma_gap_gives_more_weight():
    d0 = END - timedelta(days=3)
    one_day = ewma_trend([(END - timedelta(days=1), 80.0), (END, 81.0)])[-1][1]
    three_day = ewma_trend([(d0, 80.0), (END, 81.0)])[-1][1]
    assert three_day == pytest.approx(80 + (1 - (1 - EWMA_ALPHA) ** 3))
    assert three_day > one_day


def test_ewma_sorts_input():
    pts = [(END, 81.0), (END - timedelta(days=1), 80.0)]
    assert ewma_trend(pts)[0] == (END - timedelta(days=1), 80.0)


def test_ewma_smooths_noise():
    noise = [0.8, -0.8]
    weights = [(d, 80 + noise[i % 2]) for i, d in enumerate(days_back(30))]
    trend = [t for _, t in ewma_trend(weights)]
    raw = [w for _, w in weights]
    assert max(trend[10:]) - min(trend[10:]) < (max(raw) - min(raw)) / 4


# ---------- slope ----------

def test_linear_slope_exact_line():
    pts = [(d, 80 - 0.1 * i) for i, d in enumerate(days_back(10))]
    assert linear_slope(pts) == pytest.approx(-0.1)


def test_linear_slope_degenerate():
    assert linear_slope([]) == 0
    assert linear_slope([(END, 80)]) == 0


# ---------- adaptive TDEE ----------

def test_insufficient_data_keeps_previous():
    weights, intakes = simulate(2500, 2000, days=5)
    r = estimate_adaptive_tdee(weights, intakes, formula_tdee=2400, end_date=END, previous_tdee=2350)
    assert r.status == "insufficient_data"
    assert r.used_tdee == 2350
    assert r.warnings


def test_insufficient_data_defaults_to_formula():
    r = estimate_adaptive_tdee([], {}, formula_tdee=2400, end_date=END)
    assert r.used_tdee == 2400


def test_recovers_true_tdee_when_formula_is_right():
    # Steady state: true TDEE 2500, eating 2000 -> losing ~0.45 kg/week.
    weights, intakes = simulate(2500, 2000, days=60)
    r = estimate_adaptive_tdee(weights, intakes, formula_tdee=2500, end_date=END)
    assert r.status == "ok"
    assert r.raw_estimate == pytest.approx(2500, abs=15)
    assert r.trend_kg_per_week == pytest.approx(-500 * 7 / KCAL_PER_KG, abs=0.01)
    assert r.confidence == 1.0


def test_estimate_moves_toward_truth_and_is_rate_limited():
    # Formula says 2500 but real TDEE is 2200.
    weights, intakes = simulate(2200, 2000, days=60)
    r = estimate_adaptive_tdee(weights, intakes, formula_tdee=2500, end_date=END)
    assert r.raw_estimate == pytest.approx(2200, abs=15)
    assert r.used_tdee == pytest.approx(2500 - MAX_WEEKLY_CHANGE)
    assert any("limited" in w for w in r.warnings)


def test_repeated_checkins_converge():
    weights, intakes = simulate(2200, 2000, days=60)
    used = 2500
    for _ in range(4):
        used = estimate_adaptive_tdee(
            weights, intakes, formula_tdee=2500, end_date=END, previous_tdee=used
        ).used_tdee
    assert used == pytest.approx(2200, abs=15)


def test_noise_does_not_break_estimate():
    noise = [0.6, -0.4, 0.9, -0.7, 0.1, -0.5, 0.0]
    weights, intakes = simulate(2600, 2600, days=60, noise=noise)
    r = estimate_adaptive_tdee(weights, intakes, formula_tdee=2600, end_date=END)
    assert r.raw_estimate == pytest.approx(2600, abs=150)


def test_partial_logging_lowers_confidence_and_blends():
    weights, intakes = simulate(2200, 2000, days=60)
    sparse = {d: k for i, (d, k) in enumerate(sorted(intakes.items())) if i % 2 == 0}
    r = estimate_adaptive_tdee(weights, sparse, formula_tdee=2300, end_date=END)
    assert r.status == "ok"
    assert 0 < r.confidence < 1
    expected = r.confidence * r.raw_estimate + (1 - r.confidence) * 2300
    assert r.blended_tdee == pytest.approx(expected)


def test_implausible_estimate_is_clamped():
    # Logged intake way too low vs weight gain -> nonsense raw estimate.
    weights, _ = simulate(2500, 3500, days=40)
    intakes = {d: 500 for d in days_back(40)}
    r = estimate_adaptive_tdee(weights, intakes, formula_tdee=2500, end_date=END)
    assert r.raw_estimate == pytest.approx(2500 * 0.7)
    assert any("plausible" in w for w in r.warnings)


def test_ignores_data_after_end_date():
    weights, intakes = simulate(2500, 2000, days=60)
    future = END + timedelta(days=3)
    r1 = estimate_adaptive_tdee(weights, intakes, 2500, END)
    r2 = estimate_adaptive_tdee(weights + [(future, 50.0)], {**intakes, future: 9000}, 2500, END)
    assert r1.raw_estimate == pytest.approx(r2.raw_estimate)
