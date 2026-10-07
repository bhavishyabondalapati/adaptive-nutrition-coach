# Adaptive Nutrition Coach

An installable web app (PWA) that sets your calorie and macro targets for cutting, maintaining, or bulking, then **learns your real metabolism** from what you eat and how your weight trend moves, and adjusts your targets every week. You log food in plain English ("2 eggs and toast"), an LLM turns it into structured items, and nutrition comes from a bundled food table or USDA FoodData Central. It also builds a weekly workout plan from your goal, schedule, and equipment.

---

## 1. What it does

- **Starting targets** from the Mifflin-St Jeor BMR equation and an activity multiplier, with safety limits (max loss rate, calorie floor, warnings).
- **Adaptive TDEE**: smooths your daily weigh-ins into a trend, compares that trend with your logged calories, and estimates what you *actually* burn. Targets update weekly.
- **Natural-language food logging** via Google Gemini (default) or Claude, or an offline rule-based parser, with nutrition from a bundled CSV or USDA.
- **Weekly workout plan** that adapts to 2–6 days/week and full gym / dumbbells / bodyweight.
- **Charts** for weight (raw + trend) and daily intake vs target. Works offline as an installed app shell; light and dark themes.

## 2. Tools and libraries (and why)

| Tool | Why |
|---|---|
| **FastAPI** | Modern Python web framework; request validation with Pydantic and automatic docs at `/docs`. |
| **SQLAlchemy + SQLite** | SQLite is a single file with zero setup — perfect for a personal app. SQLAlchemy keeps the code database-agnostic. |
| **Pydantic** | Validates request bodies (e.g. age 16–100) so bad data never reaches the math. |
| **Google Gen AI SDK (Gemini)** | Default food parser. `gemini-3.5-flash-lite` is small and cheap, and a JSON response schema guarantees machine-readable output. |
| **Anthropic Python SDK (Claude)** | Optional alternative parser (`claude-haiku-4-5`) with *structured outputs*; switch with `LLM_PROVIDER=claude`. |
| **httpx** | HTTP client for the USDA API; its `MockTransport` lets tests fake USDA offline. |
| **python-dotenv** | Loads API keys from `.env` so they never live in code. |
| **pytest** | Test runner. 123 tests cover the math, parsing, planner, and API. |
| **React + Vite** | Fast dev server and build; React components keep each screen small. |
| **Recharts** | Declarative chart components for React. |
| **vite-plugin-pwa** | Generates the web app manifest and service worker that make the app installable. |

## 3. File structure

```
adaptive-nutrition-coach/
├── README.md                  This file
├── DECISIONS.md               Log of design choices and why they were made
├── requirements.txt           Python dependencies (pinned)
├── .env.example               Template for API keys (placeholders only)
├── .gitignore                 Keeps secrets, databases, and build output out of git
├── backend/
│   ├── pytest.ini             Tells pytest where the tests are
│   ├── data/foods.csv         Bundled nutrition table (47 common foods, per 100 g + unit weights)
│   ├── app/
│   │   ├── calculations.py    BMR, TDEE, calorie targets with safety caps, macro split
│   │   ├── adaptive.py        EWMA weight trend + adaptive TDEE estimate
│   │   ├── workouts.py        Rule-based weekly workout planner
│   │   ├── food_parser.py     Gemini (default) + Claude parsers + offline rule-based parser (same interface)
│   │   ├── nutrition.py       Food lookup: bundled CSV first, then USDA FoodData Central
│   │   ├── food_logging.py    Works out grams eaten and computes calories/macros
│   │   ├── db.py              SQLite tables: profile, weights, food entries, check-ins
│   │   ├── services.py        Glue between the database and the math (targets, check-ins, logging)
│   │   └── main.py            FastAPI routes under /api; serves the built frontend at /
│   └── tests/
│       ├── conftest.py        In-memory database + offline parser fixtures for API tests
│       ├── test_calculations.py  BMR / TDEE / targets / safety limits / macros
│       ├── test_adaptive.py   EWMA, slope, adaptive TDEE convergence and edge cases
│       ├── test_food.py       Parsers, CSV + mocked USDA lookups, gram resolution, fake Gemini/Claude clients, provider selection
│       ├── test_workouts.py   Planner splits, equipment, determinism
│       └── test_api.py        End-to-end API flows including a 5-week check-in simulation
├── frontend/
│   ├── index.html             HTML shell with PWA meta tags
│   ├── vite.config.js         Vite + PWA plugin config; proxies /api to FastAPI in dev
│   ├── package.json           JavaScript dependencies and scripts
│   ├── public/                Favicon and PWA icons (192, 512, maskable, Apple touch)
│   └── src/
│       ├── main.jsx           React entry point
│       ├── App.jsx            Tab navigation, onboarding, automatic weekly check-in
│       ├── api.js             Small fetch wrapper for every backend endpoint
│       ├── index.css          Design tokens (light/dark) and all styles
│       └── components/
│           ├── Today.jsx      Targets, macro progress, natural-language food log
│           ├── WeightView.jsx Weigh-in form, weight + trend chart, history
│           ├── Trends.jsx     30-day intake chart vs target, check-in history
│           ├── Plan.jsx       Weekly workout plan
│           └── ProfileForm.jsx Body stats, goal, training settings
└── scripts/
    ├── seed_demo.py           Fills the database with 6 weeks of simulated data
    └── make_icons.py          Generates the PNG app icons with only the standard library
```

## 4. Setup

```bash
# 1. Python environment (Anaconda)
conda create -n adaptive-nutrition-coach python=3.12 -y
conda activate adaptive-nutrition-coach
pip install -r requirements.txt

# 2. Frontend (needs Node 20+)
cd frontend
npm install
npm run build
cd ..

# 3. (Optional) API keys
cp .env.example .env    # then edit .env
```

All API keys are optional. `LLM_PROVIDER` picks the food parser: `gemini` (default, needs `GEMINI_API_KEY`), `claude` (needs `ANTHROPIC_API_KEY`), or `fake`. If the chosen provider has no key, the app uses the offline rule-based parser. Without `USDA_API_KEY` it only uses the bundled food table.

## 5. How to run

**Run the app** (from the project root; FastAPI serves the built frontend):

```bash
uvicorn app.main:app --app-dir backend --port 8000
```

Open http://localhost:8000. To install it, use your browser's "Install app" button (Chrome/Edge) or Share → Add to Home Screen (iPhone Safari). Note: on a phone the app needs HTTPS, except on `localhost`.

**Load demo data** (6 weeks of simulated weigh-ins and meals; replaces existing data):

```bash
python scripts/seed_demo.py
```

**Development mode** (hot reload; run each in its own terminal):

```bash
uvicorn app.main:app --app-dir backend --reload --port 8000
```

```bash
cd frontend && npm run dev
```

Then open http://localhost:5173. API docs are at http://localhost:8000/docs.

**Run the tests** (fully offline — no API keys or network needed):

```bash
pytest backend
```

## 6. How it was built

1. **Math first, as pure functions** (`calculations.py`): BMR, TDEE, targets, safety caps, macros — with hand-calculated tests.
2. **Adaptive TDEE** (`adaptive.py`): EWMA trend, least-squares slope, energy-balance estimate, confidence blending, weekly change limit — tested with simulated people whose true TDEE is known.
3. **Workout planner** (`workouts.py`): exercise library × session templates × splits; tested for coverage, equipment, determinism.
4. **Food pipeline**: bundled CSV + USDA client, an offline rule-based parser, Gemini and Claude parsers sharing one prompt and JSON schema, and gram resolution — all tested offline with mocks.
5. **Database + API** (`db.py`, `services.py`, `main.py`): SQLite tables, routes, weekly check-ins; API tests use an in-memory database and a pinned "today".
6. **React PWA**: Vite + React + Recharts, manifest + service worker, generated icons, light/dark themes.
7. **Verified in a browser** with seeded demo data at phone size in both themes, then fixed the layout issues found (clipped axis labels, wrapping table).

Each step was committed separately; see `git log`.

## The formulas

### BMR — Mifflin-St Jeor

Calories your body burns at complete rest:

```
BMR = 10 × weight(kg) + 6.25 × height(cm) − 5 × age(years) + s
s = +5 for men, −161 for women
```

Example: 80 kg, 180 cm, 30-year-old man → 800 + 1125 − 150 + 5 = **1780 kcal/day**.

### TDEE — activity multiplier

Total daily energy expenditure = BMR × activity factor:

| Level | Multiplier |
|---|---|
| Sedentary | 1.2 |
| Light (1–3 days/week) | 1.375 |
| Moderate (3–5 days/week) | 1.55 |
| Active (6–7 days/week) | 1.725 |
| Very active | 1.9 |

Example: 1780 × 1.55 = **2759 kcal/day**.

### Calorie target

Rates are a percentage of body weight per week (defaults: cut 0.5 %, bulk 0.25 %). One kg of body weight ≈ **7700 kcal**:

```
kg per week     = weight × rate% / 100
daily change    = kg per week × 7700 / 7
target calories = TDEE − daily change   (cut)
                = TDEE + daily change   (bulk)
                = TDEE                   (maintain)
```

Example: cutting at 0.5 % of 80 kg = 0.4 kg/week → 0.4 × 7700 / 7 = 440 kcal/day deficit → 2759 − 440 = **2319 kcal**.

**Safety limits** (each one adds a plain-English warning):
- Loss rate capped at **1 %/week**; gain rate capped at **0.5 %/week**.
- Calories never below **1500 (men) / 1200 (women)**. If the floor kicks in, the app recalculates the real (slower) rate.
- If protein + fat minimums don't fit, carbs are set to 0 and you're warned.

### Macros

```
protein = 2.2 g/kg (cut) or 1.8 g/kg (maintain/bulk)
fat     = max(25% of calories ÷ 9, 0.6 g/kg)
carbs   = (calories − protein×4 − fat×9) ÷ 4
```

### Weight trend — exponentially weighted moving average (EWMA)

Scale weight jumps around by 1–2 kg from water and salt. The trend smooths that out:

```
trend_today = trend_yesterday + α × (weight_today − trend_yesterday),   α = 0.1
```

Each weigh-in moves the trend 10 % of the way toward it. If you skip days, the next weigh-in counts more: `α_eff = 1 − (1 − α)^days_since_last`.

### Adaptive TDEE

Energy balance: whatever you eat beyond what you burn ends up stored (and vice versa).

```
burned = average daily intake − (trend slope in kg/day × 7700)
```

The slope is a least-squares line through the trend over the last **28 days**. Example: you average 2000 kcal and the trend drops 0.27 kg/week (−0.039 kg/day) → 2000 + 0.039 × 7700 ≈ **2300 kcal/day** actually burned.

Guard rails:
- Needs **≥10 food-logged days and ≥7 weigh-ins over ≥14 days**; otherwise keeps the current value.
- **Confidence** = logged days ÷ 21 (max 1). `TDEE = confidence × estimate + (1 − confidence) × formula`.
- Estimates outside formula **±30 %** are clamped (usually means incomplete logging).
- The TDEE used for targets moves at most **±200 kcal per weekly check-in**, so one odd week can't swing your plan.

## 7. Key concepts (interview-ready)

- **Why adaptive TDEE beats formulas**: formulas predict an average person; real people differ by ±10–20 %. Measuring intake and weight change closes the loop — it's a feedback controller.
- **Signal vs noise**: daily weight is noisy; EWMA is a simple low-pass filter. Trade-off: smoother trend = more lag (the README and `DECISIONS.md` discuss the warm-up lag).
- **Least-squares slope**: uses every point in the window, so one outlier matters less than using only the first and last values.
- **Damping**: the ±200 kcal/week limit and confidence blending stop the system from over-reacting — the same idea as a learning rate.
- **LLM for parsing, database for facts**: the model only extracts *what* you ate; nutrition numbers come from a trusted source. This avoids hallucinated calories. A JSON schema guarantees valid, parseable output.
- **Provider abstraction**: Gemini, Claude, and the rule-based parser all expose the same `parse(text)` method, so swapping providers is a one-line `.env` change and the rest of the app doesn't care.
- **Dependency injection for testability**: the parser, nutrition source, database, and even "today" are FastAPI dependencies, so tests swap in fakes and run offline.
- **Pure functions**: the math has no I/O, which makes it trivial to test exhaustively.
- **PWA basics**: a manifest (name, icons, display mode) + a service worker (caches the app shell) make a website installable and usable offline.

## Limitations

- Single user, no login. Metric units only.
- Assumes logged days are complete; unlogged days are skipped rather than counted as zero.
- Protein is based on total body weight, which overstates needs at high body-fat levels.
- Not medical advice. Talk to a professional before aggressive diets, especially with health conditions.
