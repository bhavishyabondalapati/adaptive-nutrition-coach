"""Business logic that connects the database to the pure math modules."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adaptive import WINDOW_DAYS, ewma_trend, estimate_adaptive_tdee
from .calculations import bmr_mifflin_st_jeor, compute_targets, tdee_from_activity
from .db import CheckIn, FoodEntry, Profile, WeightEntry
from .food_logging import resolve_item
from .food_parser import FakeFoodParser, FoodParseError, FoodParser
from .nutrition import NutritionService

CHECKIN_INTERVAL_DAYS = 7


def get_profile(db: Session) -> Profile | None:
    return db.get(Profile, 1)


def all_weights(db: Session) -> list[tuple[date, float]]:
    rows = db.scalars(select(WeightEntry).order_by(WeightEntry.day)).all()
    return [(r.day, r.weight_kg) for r in rows]


def current_weight(db: Session, profile: Profile) -> float:
    """Latest smoothed trend weight, or the profile weight if no weigh-ins yet."""
    trend = ewma_trend(all_weights(db))
    return trend[-1][1] if trend else profile.weight_kg


def formula_tdee(profile: Profile, weight_kg: float) -> float:
    bmr = bmr_mifflin_st_jeor(weight_kg, profile.height_cm, profile.age, profile.sex)
    return tdee_from_activity(bmr, profile.activity_level)


def latest_checkin(db: Session, only_ok: bool = False) -> CheckIn | None:
    q = select(CheckIn).order_by(CheckIn.day.desc(), CheckIn.id.desc())
    if only_ok:
        q = q.where(CheckIn.status == "ok")
    return db.scalars(q.limit(1)).first()


def checkin_due(db: Session, today: date) -> bool:
    last = latest_checkin(db)
    return last is None or (today - last.day).days >= CHECKIN_INTERVAL_DAYS


def current_targets(db: Session, profile: Profile, today: date) -> dict:
    """Targets based on the adaptive TDEE if we have one, else the formula."""
    weight = current_weight(db, profile)
    f_tdee = formula_tdee(profile, weight)
    last_ok = latest_checkin(db, only_ok=True)
    tdee = last_ok.used_tdee if last_ok else f_tdee
    targets = compute_targets(tdee, weight, profile.sex, profile.goal, profile.rate_pct)
    return {
        "targets": targets.to_dict(),
        "formula_tdee": round(f_tdee),
        "tdee_source": "adaptive" if last_ok else "formula",
        "current_weight_kg": round(weight, 2),
        "checkin_due": checkin_due(db, today),
        "last_checkin": checkin_to_dict(latest_checkin(db)),
    }


def daily_totals(db: Session, start: date, end: date) -> dict[date, dict]:
    rows = db.scalars(select(FoodEntry).where(FoodEntry.day >= start, FoodEntry.day <= end)).all()
    totals: dict[date, dict] = defaultdict(lambda: {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0})
    for r in rows:
        t = totals[r.day]
        t["kcal"] += r.kcal
        t["protein_g"] += r.protein_g
        t["carbs_g"] += r.carbs_g
        t["fat_g"] += r.fat_g
    return dict(totals)


def intake_series(db: Session, today: date, days: int) -> list[dict]:
    start = today - timedelta(days=days - 1)
    totals = daily_totals(db, start, today)
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        t = totals.get(d)
        out.append({"day": d.isoformat(), **({k: round(v) for k, v in t.items()} if t else {"kcal": None})})
    return out


def weight_series(db: Session, today: date, days: int) -> list[dict]:
    start = today - timedelta(days=days - 1)
    weights = all_weights(db)
    trend = dict(ewma_trend(weights))
    ids = {r.day: r.id for r in db.scalars(select(WeightEntry)).all()}
    return [
        {"id": ids[d], "day": d.isoformat(), "weight_kg": w, "trend_kg": round(trend[d], 2)}
        for d, w in weights
        if start <= d <= today
    ]


def checkin_to_dict(c: CheckIn | None) -> dict | None:
    if c is None:
        return None
    return {
        "id": c.id,
        "day": c.day.isoformat(),
        "status": c.status,
        "formula_tdee": round(c.formula_tdee),
        "raw_estimate": round(c.raw_estimate) if c.raw_estimate is not None else None,
        "confidence": round(c.confidence, 2),
        "used_tdee": round(c.used_tdee),
        "calories": c.calories,
        "trend_kg": c.trend_kg,
        "trend_kg_per_week": c.trend_kg_per_week,
        "warnings": json.loads(c.warnings),
    }


def run_checkin(db: Session, profile: Profile, today: date) -> dict:
    """Weekly adaptive update: estimate TDEE, store it, return new targets."""
    weight = current_weight(db, profile)
    f_tdee = formula_tdee(profile, weight)
    last_ok = latest_checkin(db, only_ok=True)
    start = today - timedelta(days=WINDOW_DAYS - 1)
    intake = {d: t["kcal"] for d, t in daily_totals(db, start, today).items()}

    result = estimate_adaptive_tdee(
        weights=all_weights(db),
        daily_intake=intake,
        formula_tdee=f_tdee,
        end_date=today,
        previous_tdee=last_ok.used_tdee if last_ok else None,
    )
    targets = compute_targets(result.used_tdee, weight, profile.sex, profile.goal, profile.rate_pct)
    checkin = CheckIn(
        day=today,
        status=result.status,
        formula_tdee=f_tdee,
        raw_estimate=result.raw_estimate,
        confidence=result.confidence,
        used_tdee=result.used_tdee,
        calories=targets.calories,
        trend_kg=result.latest_trend_kg,
        trend_kg_per_week=result.trend_kg_per_week,
        warnings=json.dumps(result.warnings),
    )
    db.add(checkin)
    db.commit()
    return {"checkin": checkin_to_dict(checkin), "estimate": result.to_dict(), "targets": targets.to_dict()}


def parse_food(text: str, parser: FoodParser, nutrition: NutritionService) -> dict:
    """Parse text and look up nutrition, without saving. Falls back to the
    offline parser if the LLM call fails."""
    warnings = []
    parser_used = parser.name
    try:
        items = parser.parse(text)
    except FoodParseError as e:
        warnings.append(f"{e}. Used the offline parser instead.")
        fallback = FakeFoodParser()
        items, parser_used = fallback.parse(text), fallback.name
    resolved = [resolve_item(i, nutrition) for i in items]
    if not resolved:
        warnings.append("No foods recognised in that text.")
    return {"items": [r.to_dict() for r in resolved], "parser": parser_used, "warnings": warnings}


def log_food(db: Session, text: str, day: date, parser: FoodParser, nutrition: NutritionService) -> dict:
    result = parse_food(text, parser, nutrition)
    entries = [FoodEntry(day=day, raw_text=text, **item) for item in result["items"]]
    db.add_all(entries)
    db.commit()
    result["items"] = [food_entry_to_dict(e) for e in entries]
    return result


def food_entry_to_dict(e: FoodEntry) -> dict:
    return {
        "id": e.id,
        "day": e.day.isoformat(),
        "raw_text": e.raw_text,
        "input_name": e.input_name,
        "matched_name": e.matched_name,
        "quantity": e.quantity,
        "unit": e.unit,
        "grams": e.grams,
        "kcal": e.kcal,
        "protein_g": e.protein_g,
        "carbs_g": e.carbs_g,
        "fat_g": e.fat_g,
        "source": e.source,
        "note": e.note,
    }
