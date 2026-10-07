"""Nutrition lookup: a small bundled CSV first, then USDA FoodData Central.

All nutrient values are per 100 g. The CSV also stores a typical unit weight
("1 egg = 50 g") because USDA search results don't include one.
"""

from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "foods.csv"
USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# USDA nutrient ids. Energy has several ids depending on the dataset.
ENERGY_IDS = (1008, 2047, 2048)  # kcal, Atwater general, Atwater specific
PROTEIN_ID, CARBS_ID, FAT_ID = 1003, 1005, 1004


@dataclass
class FoodNutrition:
    name: str
    kcal_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    source: str  # "local" or "usda"
    unit_name: str | None = None
    unit_grams: float | None = None


def normalize(name: str) -> str:
    """Lowercase, drop punctuation and simple plurals: 'Eggs!' -> 'egg'."""
    name = re.sub(r"[^a-z0-9% ]+", " ", name.lower())
    words = []
    for w in name.split():
        if len(w) > 3 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("oes"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        words.append(w)
    return " ".join(words)


class LocalFoodDB:
    """Look up foods in the bundled CSV by name or alias."""

    def __init__(self, csv_path: Path = DEFAULT_CSV):
        self.foods: dict[str, FoodNutrition] = {}
        self.index: dict[str, str] = {}  # normalized name/alias -> canonical name
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                food = FoodNutrition(
                    name=row["name"],
                    kcal_per_100g=float(row["kcal_per_100g"]),
                    protein_per_100g=float(row["protein_per_100g"]),
                    carbs_per_100g=float(row["carbs_per_100g"]),
                    fat_per_100g=float(row["fat_per_100g"]),
                    source="local",
                    unit_name=row["unit_name"] or None,
                    unit_grams=float(row["unit_grams"]) if row["unit_grams"] else None,
                )
                self.foods[food.name] = food
                for key in [food.name, *filter(None, row["aliases"].split("|"))]:
                    self.index[normalize(key)] = food.name

    def lookup(self, name: str) -> FoodNutrition | None:
        key = normalize(name)
        if key in self.index:
            return self.foods[self.index[key]]
        # Close spelling match only ("bannana" -> "banana"); a high cutoff avoids
        # nonsense like "eggplant" -> "egg".
        close = difflib.get_close_matches(key, self.index.keys(), n=1, cutoff=0.85)
        if close:
            return self.foods[self.index[close[0]]]
        return None


class USDAClient:
    """Minimal client for the FoodData Central search endpoint."""

    def __init__(self, api_key: str, http: httpx.Client | None = None):
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=10)

    def lookup(self, name: str) -> FoodNutrition | None:
        try:
            resp = self.http.get(
                USDA_SEARCH_URL,
                params={
                    "query": name,
                    "pageSize": 5,
                    # Foundation + SR Legacy are generic foods reported per 100 g.
                    "dataType": "Foundation,SR Legacy",
                    "api_key": self.api_key,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        for food in resp.json().get("foods", []):
            parsed = self._parse(food)
            if parsed:
                return parsed
        return None

    @staticmethod
    def _parse(food: dict) -> FoodNutrition | None:
        values: dict[int, float] = {}
        for n in food.get("foodNutrients", []):
            nid = n.get("nutrientId")
            if nid is not None and n.get("value") is not None:
                values[nid] = float(n["value"])
        kcal = next((values[i] for i in ENERGY_IDS if i in values), None)
        if kcal is None:
            return None
        return FoodNutrition(
            name=food.get("description", "").lower(),
            kcal_per_100g=kcal,
            protein_per_100g=values.get(PROTEIN_ID, 0.0),
            carbs_per_100g=values.get(CARBS_ID, 0.0),
            fat_per_100g=values.get(FAT_ID, 0.0),
            source="usda",
        )


class NutritionService:
    """Bundled CSV first (fast, has unit weights), then USDA if configured."""

    def __init__(self, local: LocalFoodDB, usda: USDAClient | None = None):
        self.local = local
        self.usda = usda

    def lookup(self, name: str) -> FoodNutrition | None:
        found = self.local.lookup(name)
        if found is None and self.usda is not None:
            found = self.usda.lookup(name)
        return found
