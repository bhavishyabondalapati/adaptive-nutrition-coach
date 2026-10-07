"""FastAPI app: JSON API under /api, plus the built React PWA at /."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from . import services  # noqa: E402  (load .env before modules read env vars)
from .db import CheckIn, FoodEntry, Profile, SessionLocal, WeightEntry, init_db  # noqa: E402
from .food_parser import FoodParser, get_parser  # noqa: E402
from .nutrition import LocalFoodDB, NutritionService, USDAClient  # noqa: E402
from .workouts import plan_week  # noqa: E402

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create tables on startup
    yield


app = FastAPI(title="Adaptive Nutrition Coach", lifespan=lifespan)


# ---------- dependencies (overridden in tests) ----------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@lru_cache
def get_nutrition() -> NutritionService:
    key = os.getenv("USDA_API_KEY")
    return NutritionService(LocalFoodDB(), USDAClient(key) if key else None)


@lru_cache
def get_food_parser() -> FoodParser:
    return get_parser()


def get_today() -> date:
    return date.today()


def require_profile(db: Session = Depends(get_db)) -> Profile:
    profile = services.get_profile(db)
    if profile is None:
        raise HTTPException(404, "Set up your profile first")
    return profile


# ---------- request bodies ----------

class ProfileIn(BaseModel):
    sex: Literal["male", "female"]
    age: int = Field(ge=16, le=100)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=300)
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["cut", "maintain", "bulk"]
    rate_pct: float | None = Field(default=None, ge=0, le=2)
    training_days: int = Field(default=3, ge=2, le=6)
    equipment: Literal["full_gym", "dumbbells", "bodyweight"] = "full_gym"


class WeightIn(BaseModel):
    day: date | None = None
    weight_kg: float = Field(ge=30, le=300)


class FoodIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    day: date | None = None


# ---------- routes ----------

@app.get("/api/health")
def health(parser: FoodParser = Depends(get_food_parser), nutrition: NutritionService = Depends(get_nutrition)):
    return {"status": "ok", "parser": parser.name, "usda": nutrition.usda is not None}


@app.get("/api/profile")
def read_profile(profile: Profile = Depends(require_profile)):
    return {c: getattr(profile, c) for c in ProfileIn.model_fields}


@app.put("/api/profile")
def save_profile(body: ProfileIn, db: Session = Depends(get_db)):
    profile = services.get_profile(db) or Profile(id=1)
    for k, v in body.model_dump().items():
        setattr(profile, k, v)
    db.add(profile)
    db.commit()
    return {c: getattr(profile, c) for c in ProfileIn.model_fields}


@app.get("/api/targets")
def targets(db: Session = Depends(get_db), profile: Profile = Depends(require_profile), today: date = Depends(get_today)):
    return services.current_targets(db, profile, today)


@app.get("/api/weights")
def list_weights(days: int = Query(90, ge=1, le=3650), db: Session = Depends(get_db), today: date = Depends(get_today)):
    return services.weight_series(db, today, days)


@app.post("/api/weights")
def add_weight(body: WeightIn, db: Session = Depends(get_db), today: date = Depends(get_today)):
    day = body.day or today
    entry = db.scalars(select(WeightEntry).where(WeightEntry.day == day)).first()
    if entry:  # one weigh-in per day: replace it
        entry.weight_kg = body.weight_kg
    else:
        entry = WeightEntry(day=day, weight_kg=body.weight_kg)
        db.add(entry)
    db.commit()
    return {"id": entry.id, "day": day.isoformat(), "weight_kg": entry.weight_kg}


@app.delete("/api/weights/{entry_id}")
def delete_weight(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(WeightEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()
    return {"deleted": entry_id}


@app.post("/api/food/parse")
def parse_food(
    body: FoodIn,
    parser: FoodParser = Depends(get_food_parser),
    nutrition: NutritionService = Depends(get_nutrition),
):
    """Preview what would be logged, without saving."""
    return services.parse_food(body.text, parser, nutrition)


@app.post("/api/food")
def log_food(
    body: FoodIn,
    db: Session = Depends(get_db),
    parser: FoodParser = Depends(get_food_parser),
    nutrition: NutritionService = Depends(get_nutrition),
    today: date = Depends(get_today),
):
    return services.log_food(db, body.text, body.day or today, parser, nutrition)


@app.get("/api/food")
def list_food(day: date | None = None, db: Session = Depends(get_db), today: date = Depends(get_today)):
    rows = db.scalars(select(FoodEntry).where(FoodEntry.day == (day or today)).order_by(FoodEntry.id)).all()
    return [services.food_entry_to_dict(r) for r in rows]


@app.delete("/api/food/{entry_id}")
def delete_food(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(FoodEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()
    return {"deleted": entry_id}


@app.get("/api/intake")
def intake(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), today: date = Depends(get_today)):
    return services.intake_series(db, today, days)


@app.get("/api/checkins")
def list_checkins(db: Session = Depends(get_db)):
    rows = db.scalars(select(CheckIn).order_by(CheckIn.day.desc(), CheckIn.id.desc())).all()
    return [services.checkin_to_dict(r) for r in rows]


@app.post("/api/checkins")
def create_checkin(
    force: bool = False,
    db: Session = Depends(get_db),
    profile: Profile = Depends(require_profile),
    today: date = Depends(get_today),
):
    """Run the weekly adaptive update. Without force, only runs if one is due."""
    if not force and not services.checkin_due(db, today):
        raise HTTPException(409, "Check-in not due yet")
    return services.run_checkin(db, profile, today)


@app.get("/api/workout-plan")
def workout_plan(
    goal: Literal["cut", "maintain", "bulk"] | None = None,
    days: int | None = Query(None, ge=2, le=6),
    equipment: Literal["full_gym", "dumbbells", "bodyweight"] | None = None,
    db: Session = Depends(get_db),
):
    profile = services.get_profile(db)
    goal = goal or (profile.goal if profile else "maintain")
    days = days or (profile.training_days if profile else 3)
    equipment = equipment or (profile.equipment if profile else "full_gym")
    return plan_week(goal, days, equipment)


# Serve the built frontend (npm run build) if it exists. Must come last so
# /api routes take priority.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
