"""Combine a parsed item with nutrition data: work out grams, then macros."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .food_parser import ParsedItem
from .nutrition import NutritionService

WEIGHT_UNITS = {"g": 1.0, "kg": 1000.0, "oz": 28.35, "lb": 453.6}
# Units that just mean "one of the food's normal unit".
COUNT_UNITS = {None, "piece", "serving", "whole", "item"}
DEFAULT_GRAMS = 100.0


@dataclass
class ResolvedItem:
    input_name: str
    matched_name: str | None
    quantity: float
    unit: str | None
    grams: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    source: str  # "local", "usda" or "unknown"
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_grams(item: ParsedItem, unit_name: str | None, unit_grams: float | None) -> tuple[float, str | None]:
    """Decide how many grams the person ate. Returns (grams, note).

    Order of trust:
    1. An explicit weight unit ("150 g", "6 oz") - exact.
    2. The food's own unit from our CSV ("2 eggs", "1 slice toast").
    3. The LLM's gram estimate.
    4. Our CSV unit weight even if the units don't match, with a note.
    5. 100 g per item, with a note.
    """
    if item.unit in WEIGHT_UNITS:
        return item.quantity * WEIGHT_UNITS[item.unit], None
    if unit_grams and (item.unit in COUNT_UNITS or item.unit == unit_name):
        return item.quantity * unit_grams, None
    if item.grams_estimate:
        return item.grams_estimate, None
    if unit_grams:
        return item.quantity * unit_grams, f"Assumed 1 {item.unit} = 1 {unit_name} ({unit_grams:g} g)"
    return item.quantity * DEFAULT_GRAMS, f"Portion unknown; assumed {DEFAULT_GRAMS:g} g each"


def resolve_item(item: ParsedItem, nutrition: NutritionService) -> ResolvedItem:
    food = nutrition.lookup(item.name)
    if food is None:
        grams, note = resolve_grams(item, None, None)
        return ResolvedItem(
            input_name=item.name, matched_name=None, quantity=item.quantity, unit=item.unit,
            grams=round(grams, 1), kcal=0, protein_g=0, carbs_g=0, fat_g=0,
            source="unknown", note="Food not found; nutrition not counted",
        )
    grams, note = resolve_grams(item, food.unit_name, food.unit_grams)
    f = grams / 100
    return ResolvedItem(
        input_name=item.name,
        matched_name=food.name,
        quantity=item.quantity,
        unit=item.unit,
        grams=round(grams, 1),
        kcal=round(food.kcal_per_100g * f, 1),
        protein_g=round(food.protein_per_100g * f, 1),
        carbs_g=round(food.carbs_per_100g * f, 1),
        fat_g=round(food.fat_per_100g * f, 1),
        source=food.source,
        note=note,
    )
