"""Food parsing + nutrition lookup tests. All offline: no real LLM or USDA calls."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.food_logging import resolve_item
from app.food_parser import ClaudeFoodParser, FakeFoodParser, FoodParseError, ParsedItem
from app.nutrition import LocalFoodDB, NutritionService, USDAClient, normalize


@pytest.fixture(scope="module")
def local():
    return LocalFoodDB()


@pytest.fixture
def service(local):
    return NutritionService(local)


# ---------- rule-based parser ----------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("2 eggs and toast", [("eggs", 2, None), ("toast", 1, None)]),
        ("150g chicken breast", [("chicken breast", 150, "g")]),
        ("1 cup of rice, a banana", [("rice", 1, "cup"), ("banana", 1, None)]),
        ("half a cup of oatmeal with 1 tbsp peanut butter", [("oatmeal", 0.5, "cup"), ("peanut butter", 1, "tbsp")]),
        ("1 1/2 cups milk", [("milk", 1.5, "cup")]),
        ("1/2 avocado", [("avocado", 0.5, None)]),
        ("two large eggs", [("eggs", 2, None)]),
        ("6 oz salmon + broccoli", [("salmon", 6, "oz"), ("broccoli", 1, None)]),
        ("1 cup 2% milk", [("2% milk", 1, "cup")]),
    ],
)
def test_fake_parser(text, expected):
    items = FakeFoodParser().parse(text)
    assert [(i.name, i.quantity, i.unit) for i in items] == expected


def test_fake_parser_empty():
    assert FakeFoodParser().parse("  , and ") == []


# ---------- local CSV ----------

def test_normalize_plurals():
    assert normalize("Eggs!") == "egg"
    assert normalize("Strawberries") == "strawberry"
    assert normalize("potatoes") == "potato"
    assert normalize("glass") == "glass"


@pytest.mark.parametrize(
    "query, name",
    [("eggs", "egg"), ("Toast", "toast"), ("rice", "white rice"), ("bannana", "banana"), ("chicken", "chicken breast")],
)
def test_local_lookup(local, query, name):
    assert local.lookup(query).name == name


def test_local_lookup_does_not_overmatch(local):
    assert local.lookup("eggplant") is None
    assert local.lookup("dragon fruit") is None


# ---------- USDA client (mocked HTTP) ----------

USDA_RESPONSE = {
    "foods": [
        {"description": "No energy food", "foodNutrients": [{"nutrientId": 1003, "value": 5}]},
        {
            "description": "Mango, raw",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 60},
                {"nutrientId": 1003, "value": 0.8},
                {"nutrientId": 1005, "value": 15},
                {"nutrientId": 1004, "value": 0.4},
            ],
        },
    ]
}


def make_usda(response_json=None, status=200):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(status, json=response_json or {})

    return USDAClient("TEST_KEY", http=httpx.Client(transport=httpx.MockTransport(handler))), seen


def test_usda_parses_first_food_with_energy():
    usda, seen = make_usda(USDA_RESPONSE)
    food = usda.lookup("mango")
    assert food.name == "mango, raw"
    assert (food.kcal_per_100g, food.protein_per_100g, food.carbs_per_100g, food.fat_per_100g) == (60, 0.8, 15, 0.4)
    assert food.source == "usda"
    assert seen["params"]["query"] == "mango"


def test_usda_uses_atwater_energy_when_kcal_missing():
    usda, _ = make_usda({"foods": [{"description": "X", "foodNutrients": [{"nutrientId": 2047, "value": 77}]}]})
    assert usda.lookup("x").kcal_per_100g == 77


def test_usda_http_error_returns_none():
    usda, _ = make_usda(status=500)
    assert usda.lookup("mango") is None


def test_service_falls_back_to_usda(local):
    usda, _ = make_usda(USDA_RESPONSE)
    service = NutritionService(local, usda)
    assert service.lookup("egg").source == "local"
    assert service.lookup("mango").source == "usda"


# ---------- grams + macros ----------

def test_two_eggs(service):
    r = resolve_item(ParsedItem("eggs", 2), service)
    assert r.grams == 100
    assert r.kcal == 143
    assert r.protein_g == 12.6


def test_weight_units_win(service):
    r = resolve_item(ParsedItem("chicken breast", 6, "oz", grams_estimate=999), service)
    assert r.grams == pytest.approx(170.1)
    assert r.kcal == pytest.approx(165 * 1.701, abs=0.1)


def test_matching_food_unit(service):
    assert resolve_item(ParsedItem("rice", 1, "cup"), service).grams == 158


def test_llm_estimate_used_for_unknown_unit(service):
    r = resolve_item(ParsedItem("rice", 1, "bowl", grams_estimate=250), service)
    assert r.grams == 250 and r.note is None


def test_mismatched_unit_without_estimate_adds_note(service):
    r = resolve_item(ParsedItem("rice", 1, "bowl"), service)
    assert r.grams == 158 and "Assumed" in r.note


def test_unknown_food_counts_zero(service):
    r = resolve_item(ParsedItem("dragon fruit", 1), service)
    assert r.source == "unknown" and r.kcal == 0 and r.note


def test_usda_food_uses_llm_grams(local):
    usda, _ = make_usda(USDA_RESPONSE)
    r = resolve_item(ParsedItem("mango", 1, None, grams_estimate=200), NutritionService(local, usda))
    assert r.grams == 200 and r.kcal == 120


# ---------- Claude parser with a fake client ----------

class FakeClaudeClient:
    """Mimics client.beta.messages.create and records the request."""

    def __init__(self, payload=None, stop_reason="end_turn"):
        self.payload, self.stop_reason, self.calls = payload, stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = [SimpleNamespace(type="text", text=json.dumps(self.payload))]
        return SimpleNamespace(content=content, stop_reason=self.stop_reason)


def test_claude_parser_maps_structured_output():
    client = FakeClaudeClient(
        {"items": [
            {"name": "Egg", "quantity": 2, "unit": "", "grams_estimate": 100},
            {"name": "white bread", "quantity": 1, "unit": "Slice", "grams_estimate": 30},
        ]}
    )
    items = ClaudeFoodParser(client=client, model="test-model").parse("2 eggs and toast")
    assert items == [
        ParsedItem("egg", 2, None, 100),
        ParsedItem("white bread", 1, "slice", 30),
    ]
    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["messages"][0]["content"] == "2 eggs and toast"


def test_claude_parser_refusal_raises():
    with pytest.raises(FoodParseError):
        ClaudeFoodParser(client=FakeClaudeClient({"items": []}, "refusal")).parse("x")
