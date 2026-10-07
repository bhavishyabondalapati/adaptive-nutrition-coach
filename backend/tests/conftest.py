"""Shared fixtures: an in-memory database and offline parser/nutrition for API tests."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.db import Base
from app.food_parser import FakeFoodParser
from app.nutrition import LocalFoodDB, NutritionService

TODAY = date(2026, 3, 31)


@pytest.fixture
def client():
    # StaticPool keeps a single in-memory connection so all sessions see the same data.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides = {
        main.get_db: get_db,
        main.get_food_parser: FakeFoodParser,
        main.get_nutrition: lambda: NutritionService(LocalFoodDB()),
        main.get_today: lambda: TODAY,
    }
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides = {}
