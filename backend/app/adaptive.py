"""Adaptive TDEE: estimate real energy expenditure from what you eat and how
your (smoothed) weight changes.

The idea is energy balance:

    intake - expenditure = stored energy
    expenditure = average intake - (weight change in kg/day x 7700 kcal/kg)

Daily scale weight is noisy (water, salt, glycogen), so we first smooth it into
a trend with an exponentially weighted moving average (EWMA) and use the slope
of that trend instead of raw weigh-ins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .calculations import KCAL_PER_KG

EWMA_ALPHA = 0.1  # weight on each new weigh-in (Hacker's Diet uses 0.1)
WINDOW_DAYS = 28  # look-back window for the estimate
MIN_INTAKE_DAYS = 10  # need at least this many logged food days in the window
MIN_WEIGH_INS = 7  # ...and this many weigh-ins
MIN_SPAN_DAYS = 14  # ...spread over at least this many days
FULL_CONFIDENCE_DAYS = 21  # logged days needed before we fully trust the estimate
MAX_WEEKLY_CHANGE = 200  # max kcal the TDEE we use may move in one weekly check-in
PLAUSIBLE_BAND = 0.30  # raw estimates outside formula +/- 30% are clamped


def ewma_trend(weights: list[tuple[date, float]], alpha: float = EWMA_ALPHA) -> list[tuple[date, float]]:
    """Smooth weigh-ins into a trend line.

    trend_today = trend_yesterday + a * (weight_today - trend_yesterday)

    If you skip days, the new weigh-in gets a bigger weight
    (a_eff = 1 - (1 - a)^gap_days), as if it had been seen on each missed day.
    The first weigh-in starts the trend.
    """
    if not weights:
        return []
    pts = sorted(weights)
    trend = pts[0][1]
    out = [(pts[0][0], trend)]
    prev_day = pts[0][0]
    for day, w in pts[1:]:
        gap = max((day - prev_day).days, 1)
        a_eff = 1 - (1 - alpha) ** gap
        trend = trend + a_eff * (w - trend)
        out.append((day, trend))
        prev_day = day
    return out


def linear_slope(points: list[tuple[date, float]]) -> float:
    """Least-squares slope (units per day) of (date, value) points."""
    if len(points) < 2:
        return 0.0
    x0 = points[0][0]
    xs = [(d - x0).days for d, _ in points]
    ys = [v for _, v in points]
    n = len(points)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / sxx


@dataclass
class AdaptiveResult:
    status: str  # "ok" or "insufficient_data"
    formula_tdee: float
    raw_estimate: float | None  # pure energy-balance number
    confidence: float  # 0..1, how much we trust raw_estimate
    blended_tdee: float  # mix of formula and raw estimate by confidence
    used_tdee: float  # blended, limited to +/- MAX_WEEKLY_CHANGE from last week
    avg_intake: float | None
    trend_kg_per_week: float | None
    latest_trend_kg: float | None
    intake_days: int
    weigh_ins: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("raw_estimate", "blended_tdee", "used_tdee", "avg_intake", "formula_tdee"):
            if d[k] is not None:
                d[k] = round(d[k])
        for k in ("trend_kg_per_week", "latest_trend_kg"):
            if d[k] is not None:
                d[k] = round(d[k], 3)
        d["confidence"] = round(d["confidence"], 2)
        return d


def estimate_adaptive_tdee(
    weights: list[tuple[date, float]],
    daily_intake: dict[date, float],
    formula_tdee: float,
    end_date: date,
    previous_tdee: float | None = None,
    window_days: int = WINDOW_DAYS,
) -> AdaptiveResult:
    """Estimate TDEE from the last `window_days` of data ending at `end_date`.

    - `weights`: all weigh-ins (older ones are used to warm up the trend).
    - `daily_intake`: kcal per day, only for days the user logged food.
    - `previous_tdee`: TDEE used at the last check-in (defaults to formula).
    """
    start = end_date - timedelta(days=window_days - 1)
    trend = ewma_trend([w for w in weights if w[0] <= end_date])
    window_trend = [(d, t) for d, t in trend if start <= d <= end_date]
    window_intake = {d: k for d, k in daily_intake.items() if start <= d <= end_date and k > 0}
    previous = formula_tdee if previous_tdee is None else previous_tdee
    latest_trend = trend[-1][1] if trend else None

    base = dict(
        formula_tdee=formula_tdee,
        intake_days=len(window_intake),
        weigh_ins=len(window_trend),
        latest_trend_kg=latest_trend,
    )

    span = (window_trend[-1][0] - window_trend[0][0]).days if len(window_trend) >= 2 else 0
    if (
        len(window_intake) < MIN_INTAKE_DAYS
        or len(window_trend) < MIN_WEIGH_INS
        or span < MIN_SPAN_DAYS
    ):
        return AdaptiveResult(
            status="insufficient_data",
            raw_estimate=None,
            confidence=0.0,
            blended_tdee=formula_tdee,
            used_tdee=previous,
            avg_intake=None,
            trend_kg_per_week=None,
            warnings=[
                f"Need {MIN_INTAKE_DAYS}+ food-logged days and {MIN_WEIGH_INS}+ weigh-ins "
                f"over {MIN_SPAN_DAYS}+ days in the last {window_days} days. Using the "
                "current estimate for now."
            ],
            **base,
        )

    warnings: list[str] = []
    avg_intake = sum(window_intake.values()) / len(window_intake)
    slope_kg_per_day = linear_slope(window_trend)
    raw = avg_intake - slope_kg_per_day * KCAL_PER_KG

    lo, hi = formula_tdee * (1 - PLAUSIBLE_BAND), formula_tdee * (1 + PLAUSIBLE_BAND)
    if not lo <= raw <= hi:
        warnings.append(
            f"Estimated expenditure ({raw:.0f} kcal) is far from the formula ({formula_tdee:.0f}); "
            "check that food logs are complete. Clamped to a plausible range."
        )
        raw = min(max(raw, lo), hi)

    confidence = min(1.0, len(window_intake) / FULL_CONFIDENCE_DAYS)
    blended = confidence * raw + (1 - confidence) * formula_tdee

    used = min(max(blended, previous - MAX_WEEKLY_CHANGE), previous + MAX_WEEKLY_CHANGE)
    if used != blended:
        warnings.append(
            f"Change limited to {MAX_WEEKLY_CHANGE} kcal this week to avoid over-reacting; "
            "it will keep adjusting at future check-ins."
        )

    return AdaptiveResult(
        status="ok",
        raw_estimate=raw,
        confidence=confidence,
        blended_tdee=blended,
        used_tdee=used,
        avg_intake=avg_intake,
        trend_kg_per_week=slope_kg_per_day * 7,
        warnings=warnings,
        **base,
    )
