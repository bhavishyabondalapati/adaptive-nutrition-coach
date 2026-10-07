"""Fill the database with 6 weeks of realistic demo data.

Simulates someone on a cut whose real TDEE (2450 kcal) is lower than the
formula predicts, so you can watch the adaptive TDEE correct it.

Run from the project root (WARNING: replaces all existing data):
    python scripts/seed_demo.py
"""

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.calculations import KCAL_PER_KG  # noqa: E402
from app.db import Base, CheckIn, Profile, SessionLocal, WeightEntry, engine  # noqa: E402
from app.food_parser import FakeFoodParser  # noqa: E402
from app.nutrition import LocalFoodDB, NutritionService  # noqa: E402
from app.services import log_food, run_checkin  # noqa: E402

TRUE_TDEE = 2450
DAYS = 42
MEALS = {
    "breakfast": ["3 eggs and 2 slices toast", "1 cup oatmeal with a banana and 1 scoop whey protein", "1 container greek yogurt with 1 cup blueberries and 1 serving granola"],
    "lunch": ["1 chicken breast with 1.5 cups rice and 1 cup broccoli", "1 can tuna with 2 slices whole wheat bread and 1 apple", "1 cup lentils, 1 cup brown rice and 1 tbsp olive oil"],
    "dinner": ["1 salmon fillet with 1 potato and 2 cups spinach", "2 cups pasta with 1 ground beef patty", "1.5 chicken breast with 1 sweet potato and 1 tbsp butter"],
    "snack": ["1 tbsp peanut butter and 1 banana", "1 handful almonds", "1 cup milk and 2 squares dark chocolate", "1 orange"],
}


def main() -> None:
    random.seed(7)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(Profile(id=1, sex="male", age=29, height_cm=178, weight_kg=84.0,
                   activity_level="moderate", goal="cut", rate_pct=0.5,
                   training_days=4, equipment="full_gym"))
    db.commit()

    parser, nutrition = FakeFoodParser(), NutritionService(LocalFoodDB())
    today = date.today()
    true_weight_kg = 84.0
    profile = db.get(Profile, 1)
    for i in range(DAYS, 0, -1):
        day = today - timedelta(days=i - 1)
        # Daily scale weight = true weight + water noise; skip ~1 in 7 weigh-ins.
        if random.random() > 0.15:
            noise = random.gauss(0, 0.35)
            db.add(WeightEntry(day=day, weight_kg=round(true_weight_kg + noise, 1)))
            db.commit()
        kcal = 0.0
        if random.random() > 0.1:  # forget to log ~1 day in 10
            for meal in ("breakfast", "lunch", "dinner", "snack", "snack"):
                r = log_food(db, random.choice(MEALS[meal]), day, parser, nutrition)
                kcal += sum(item["kcal"] for item in r["items"])
        else:
            kcal = 2100  # still ate, just didn't log
        true_weight_kg += (kcal - TRUE_TDEE) / KCAL_PER_KG
        # Weekly check-in every 7 days, like the app does.
        if i % 7 == 1 and i < DAYS - 7:
            run_checkin(db, profile, day)

    print(f"Seeded {DAYS} days. Check-ins: {db.query(CheckIn).count()}. Final weight ~{true_weight_kg:.1f} kg")
    db.close()


if __name__ == "__main__":
    main()
