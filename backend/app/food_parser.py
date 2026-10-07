"""Turn free text like "2 eggs and toast" into structured food items.

Two parsers share one interface:
- ClaudeFoodParser: asks Claude to extract items (handles messy language).
- FakeFoodParser: a small rule-based parser. Used in tests and whenever no
  API key is configured, so the app works fully offline.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Protocol

DEFAULT_MODEL = "claude-opus-5-5"


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
# Claude parser
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


class ClaudeFoodParser:
    """Food parser backed by the Claude API with structured JSON output."""

    name = "claude"

    def __init__(self, client=None, model: str | None = None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)

    def parse(self, text: str) -> list[ParsedItem]:
        import anthropic

        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
                # Simple extraction: low effort keeps it fast and cheap.
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
                },
                # If a safety classifier declines, retry on a fallback model in the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIConnectionError as e:
            raise FoodParseError("Could not reach the Claude API") from e
        except anthropic.APIStatusError as e:
            raise FoodParseError(f"Claude API error ({e.status_code})") from e

        if response.stop_reason == "refusal":
            raise FoodParseError("The model declined to parse this text")
        if response.stop_reason == "max_tokens":
            raise FoodParseError("The model's answer was cut off")
        text_block = next((b.text for b in response.content if b.type == "text"), None)
        if text_block is None:
            raise FoodParseError("No text in model response")
        try:
            data = json.loads(text_block)
        except json.JSONDecodeError as e:
            raise FoodParseError("Model returned invalid JSON") from e

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


def get_parser() -> FoodParser:
    """Pick the parser from env: LLM_PROVIDER=claude|fake.

    Default: Claude when ANTHROPIC_API_KEY is set, otherwise the offline parser.
    """
    provider = os.getenv("LLM_PROVIDER")
    if provider is None:
        provider = "claude" if os.getenv("ANTHROPIC_API_KEY") else "fake"
    if provider == "claude":
        return ClaudeFoodParser()
    return FakeFoodParser()
