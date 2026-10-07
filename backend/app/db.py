"""SQLite database setup and tables (SQLAlchemy 2.0 style).

This is a single-user app: there's one profile row (id=1).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DEFAULT_DB = Path(__file__).resolve().parent.parent / "coach.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}")


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sex: Mapped[str] = mapped_column(String(10))
    age: Mapped[int] = mapped_column(Integer)
    height_cm: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)  # starting weight; weigh-ins take over
    activity_level: Mapped[str] = mapped_column(String(20))
    goal: Mapped[str] = mapped_column(String(10))
    rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_days: Mapped[int] = mapped_column(Integer, default=3)
    equipment: Mapped[str] = mapped_column(String(20), default="full_gym")


class WeightEntry(Base):
    __tablename__ = "weights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)


class FoodEntry(Base):
    __tablename__ = "food_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    input_name: Mapped[str] = mapped_column(String(200))
    matched_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    grams: Mapped[float] = mapped_column(Float)
    kcal: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CheckIn(Base):
    """One weekly adaptive-TDEE update."""

    __tablename__ = "checkins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30))
    formula_tdee: Mapped[float] = mapped_column(Float)
    raw_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    used_tdee: Mapped[float] = mapped_column(Float)
    calories: Mapped[int] = mapped_column(Integer)
    trend_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_kg_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings: Mapped[str] = mapped_column(Text, default="[]")  # JSON list


def make_engine(url: str = DATABASE_URL):
    # check_same_thread=False lets FastAPI's thread pool share the SQLite connection.
    return create_engine(url, connect_args={"check_same_thread": False})


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind=None) -> None:
    Base.metadata.create_all(bind=bind or engine)
