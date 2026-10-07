"""Turn free text like "2 eggs and toast" into structured food items.

Three parsers share one interface (a `parse(text)` method):
- GeminiFoodParser (default): asks Google Gemini to extract items.
- ClaudeFoodParser: same job using Anthropic's Claude.
- FakeFoodParser: a small rule-based parser. Used in tests and whenever no
  API key is configured, so the app works fully offline.

Both LLM parsers use a small, cheap model and a JSON schema, so the reply is
always machine-readable. Choose one with LLM_PROVIDER in .env.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Protocol

import httpx

# Small, cheap models: this is a simple extraction task.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"


@dataclass
class ParsedItem:
    name: str
    quantity: float = 1.0
    unit: str | None = None  # "g", "cup", "slice", ... or None for "one of the thing"
    grams_estimate: float | None = None  # model's best guess at total grams

    def to_dict(self) -> dict:
        return asdict(self)


class FoodParser(Protocol):
    name: str

    def parse(self, text: str) -> list[ParsedItem]: ...


class FoodParseError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Rule-based parser
# ---------------------------------------------------------------------------

WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "half": 0.5,
    "couple": 2, "few": 3, "dozen": 12,
}
# Spoken unit -> canonical unit.
UNITS = {
    "g": "g", "gram": "g", "grams": "g", "gr": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "ml": "ml",
    "cup": "cup", "cups": "cup",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "slice": "slice", "slices": "slice",
    "piece": "piece", "pieces": "piece",
    "scoop": "scoop", "scoops": "scoop",
    "serving": "serving", "servings": "serving",
    "can": "can", "cans": "can",
    "handful": "handful", "handfuls": "handful",
    "bowl": "bowl", "bowls": "bowl",
    "glass": "glass", "glasses": "glass",
    "fillet": "fillet", "fillets": "fillet",
    "square": "square", "squares": "square",
}
FILLER = {"of", "some", "small", "medium", "large", "big", "plain", "fresh"}
SPLIT_RE = re.compile(r",|;|\+|&|\band\b|\bwith\b|\bplus\b")
NUM_RE = re.compile(r"^(\d+\s+\d+/\d+|\d+/\d+|\d*\.?\d+)\s*([a-z]+)?$")


def _to_number(token: str) -> float:
    token = token.strip()
    if " " in token:  # mixed number "1 1/2"
        whole, frac = token.split()
        return float(int(whole) + Fraction(frac))
    return float(Fraction(token)) if "/" in token else float(token)


class FakeFoodParser:
    """Deterministic parser for simple phrases: '[qty] [unit] [of] food'."""

    name = "rule-based"

    def parse(self, text: str) -> list[ParsedItem]:
        items = []
        for chunk in SPLIT_RE.split(text.lower()):
            item = self._parse_chunk(chunk)
            if item:
                items.append(item)
        return items

    def _parse_chunk(self, chunk: str) -> ParsedItem | None:
        words = re.sub(r"[^a-z0-9./% ]+", " ", chunk).split()
        if not words:
            return None
        quantity, unit = 1.0, None

        # Quantity: "2", "1.5", "1/2", "1 1/2", "100g", or a number word.
        first = words[0]
        if len(words) > 1 and re.fullmatch(r"\d+", first) and re.fullmatch(r"\d+/\d+", words[1]):
            quantity, words = _to_number(f"{first} {words[1]}"), words[2:]
        elif m := NUM_RE.match(first):
            quantity = _to_number(m.group(1))
            if m.group(2) in UNITS:
                unit = UNITS[m.group(2)]
            words = words[1:]
        elif first in WORD_NUMBERS:
            quantity = WORD_NUMBERS[first]
            words = words[1:]
            if words and words[0] in ("a", "an", "of"):  # "half a cup", "couple of eggs"
                words = words[1:]

        # Unit, then filler words like "of" / "large".
        while words and words[0] in FILLER:
            words = words[1:]
        if unit is None and words and words[0] in UNITS:
            unit = UNITS[words[0]]
            words = words[1:]
        while words and words[0] in FILLER:
            words = words[1:]

        name = " ".join(words).strip()
        if not name:
            return None
        return ParsedItem(name=name, quantity=quantity, unit=unit)


# ---------------------------------------------------------------------------
# LLM parsers (shared prompt + schema)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You turn a person's description of what they ate into a list of foods.

For each distinct food, return:
- name: a short, generic food name a nutrition database would recognise
  (e.g. "egg", "white bread", "chicken breast", "white rice"). Split mixed
  dishes into components when they're obviously separate ("eggs and toast"
  -> two items); keep a named dish as one item ("lasagna").
- quantity: the number the person said, or 1 if they gave none.
- unit: the unit they used, lowercase singular ("g", "oz", "cup", "slice",
  "tbsp", "scoop"), or "" when they just counted whole items ("2 eggs").
- grams_estimate: your best estimate of the TOTAL edible grams for that line
  (e.g. "2 eggs" -> 100, "a bowl of rice" -> 200).

Only include food and drink. If the text contains no food, return an empty list."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "grams_estimate": {"type": "number"},
                },
                "required": ["name", "quantity", "unit", "grams_estimate"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def items_from_json(raw: str | None) -> list[ParsedItem]:
    """Convert the model's JSON reply into ParsedItems (same for every provider)."""
    if not raw:
        raise FoodParseError("No text in model response")
    try:
        data = json.loads(raw)
        return [
            ParsedItem(
                name=i["name"].strip().lower(),
                quantity=float(i["quantity"]) or 1.0,
                unit=(i["unit"].strip().lower() or None),
                grams_estimate=float(i["grams_estimate"]) if i["grams_estimate"] > 0 else None,
            )
            for i in data["items"]
            if i["name"].strip()
        ]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        raise FoodParseError("Model returned invalid JSON") from e


class GeminiFoodParser:
    """Food parser backed by Google Gemini with a JSON response schema."""

    name = "gemini"

    def __init__(self, client=None, model: str | None = None):
        if client is None:
            from google import genai

            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.client = client
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    def parse(self, text: str) -> list[ParsedItem]:
        from google.genai import errors, types

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=OUTPUT_SCHEMA,
                    temperature=0,
                ),
            )
        except errors.APIError as e:
            raise FoodParseError(f"Gemini API error ({e.code})") from e
        except httpx.HTTPError as e:  # the SDK uses httpx for network calls
            raise FoodParseError("Could not reach the Gemini API") from e
        return items_from_json(response.text)


class ClaudeFoodParser:
    """Food parser backed by the Claude API with structured JSON output."""

    name = "claude"

    def __init__(self, client=None, model: str | None = None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)

    def parse(self, text: str) -> list[ParsedItem]:
        import anthropic

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,  # a list of a few foods is short
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
                output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            )
        except anthropic.APIConnectionError as e:
            raise FoodParseError("Could not reach the Claude API") from e
        except anthropic.APIStatusError as e:
            raise FoodParseError(f"Claude API error ({e.status_code})") from e

        if response.stop_reason == "refusal":
            raise FoodParseError("The model declined to parse this text")
        if response.stop_reason == "max_tokens":
            raise FoodParseError("The model's answer was cut off")
        return items_from_json(next((b.text for b in response.content if b.type == "text"), None))


PROVIDERS = {"gemini": GeminiFoodParser, "claude": ClaudeFoodParser, "fake": FakeFoodParser}
API_KEY_ENV = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def get_parser() -> FoodParser:
    """Pick the parser from LLM_PROVIDER (gemini | claude | fake). Default: gemini.

    If the chosen provider has no API key, use the offline parser instead so
    the app still works.
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {list(PROVIDERS)}, got {provider!r}")
    key_var = API_KEY_ENV.get(provider)
    if key_var and not os.getenv(key_var):
        provider = "fake"
    return PROVIDERS[provider]()
