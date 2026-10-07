# Design decisions

A running log of choices made while building this project, and why.

## Math

- **Mifflin-St Jeor for BMR.** It is the equation the Academy of Nutrition and
  Dietetics found most accurate for healthy adults, and it only needs weight,
  height, age and sex.
- **Standard activity multipliers** (1.2 / 1.375 / 1.55 / 1.725 / 1.9). They are
  rough, which is exactly why the adaptive TDEE exists.
- **7700 kcal per kg** of body-weight change. Standard planning approximation.
- **Rates are a % of body weight per week**, not fixed kg, so they scale with
  body size. Defaults: cut 0.5 %/wk, bulk 0.25 %/wk.
- **Safety caps:** loss capped at 1 %/wk, gain at 0.5 %/wk, and calories never
  below 1500 (male) / 1200 (female). When a cap or floor is hit the app returns a
  plain-English warning and recomputes the *real* rate that is achievable.
- **Macros:** protein 2.2 g/kg on a cut (protects muscle), 1.8 g/kg otherwise;
  fat 25 % of calories with a 0.6 g/kg minimum; carbs fill the rest (never < 0).
  Macros use current body weight, which overstates protein for people with high
  body fat; acceptable for a learning project and noted in the README.

## Adaptive TDEE

- **EWMA trend (alpha = 0.1)** like John Walker's *Hacker's Diet*. Simple,
  explainable, needs no library. When days are skipped the new weigh-in gets
  `1 - (1 - alpha)^gap` weight, as if it had been seen on every missed day.
- **Slope via least squares over the trend points in the window** instead of
  just (last - first). Uses every point, so one odd day matters less.
- **Window 28 days; needs >= 10 food-logged days, >= 7 weigh-ins over >= 14
  days.** Below that we keep the previous TDEE and say why.
- **Unlogged days are skipped, not treated as 0 kcal.** Average intake is over
  logged days only. Assumes logged days are complete.
- **Confidence blending:** confidence = logged days / 21 (max 1). The TDEE is
  `confidence * estimate + (1 - confidence) * formula`.
- **Weekly change limited to +/-200 kcal** so one noisy week can't swing
  targets wildly; repeated check-ins converge (tested).
- **Plausibility clamp:** raw estimates outside formula +/-30 % are clamped with a
  warning; that's almost always incomplete food logging.

## Food logging

- **Three parsers, one interface.** `GeminiFoodParser` (default) and
  `ClaudeFoodParser` share the same prompt and JSON schema, so the reply always
  matches a fixed shape; `FakeFoodParser` is a small rule-based parser used in
  tests and whenever no API key is set, so the whole app runs offline. If an LLM
  call fails, the API falls back to the rule-based parser and says so.
- **Gemini is the default provider** (`LLM_PROVIDER=gemini|claude|fake`). If the
  chosen provider's key is missing, the app quietly uses the offline parser
  rather than crashing. An unknown provider name is an error.
- **Small, cheap models for both:** `gemini-3.5-flash-lite` (latest general
  Flash-Lite on Google's model list as of Oct 2026) and `claude-haiku-4-5`.
  Splitting "2 eggs and toast" into items is easy; a big model adds cost and
  latency for no gain. Both are overridable (`GEMINI_MODEL`, `CLAUDE_MODEL`).
  Gemini runs at temperature 0 for repeatable output. (Replaces the earlier
  `claude-opus-5-5` choice.)
- **The LLM only parses; it never invents nutrition numbers.** Nutrition comes
  from the bundled CSV or USDA. The LLM's only number is a gram estimate for
  portions like "a bowl of rice".
- **Lookup order: bundled CSV, then USDA FoodData Central.** The CSV is fast,
  offline, and has unit weights ("1 egg = 50 g"); USDA covers everything else.
  USDA search is limited to Foundation + SR Legacy data (generic foods, per 100 g).
- **Grams resolution order:** explicit weight unit > the food's own unit in
  the CSV > LLM estimate > CSV unit with a note > 100 g with a note.
- **Unknown foods are saved with 0 kcal and a note**, not silently dropped, so
  the user can see what wasn't counted.
- **Known limitation: EWMA warm-up lag.** The trend starts at the first
  weigh-in, so in the first ~2-3 weeks its slope under-reads a steady loss/gain
  (about 15 % of the deficit after 5 weeks of data). That's small compared with
  formula error, and the confidence blend + weekly limit already make early
  check-ins cautious.

## Backend / API

- **Single-user app** (one profile row, id = 1). Fine for a personal PWA; adding
  users would mean a `user_id` column and auth.
- **Adaptive TDEE only overrides the formula after an "ok" check-in.** Check-ins
  with too little data are still stored (so you see why) but targets keep using
  the live formula, which also reacts to profile edits.
- **Check-ins run at most weekly** (409 if not due, `?force=true` to override).
  The frontend triggers a check-in automatically when one is due.
- **One weigh-in per day**; posting again replaces it.
- **`today` is a dependency** so tests can pin the date.
- **Production serving:** FastAPI serves the built frontend from
  `frontend/dist`, so one `uvicorn` command runs the whole app.

## Frontend

- **Vite + React (plain JavaScript, no TypeScript)** to keep the learning curve
  small. **Recharts** for charts: declarative React components, good defaults.
- **vite-plugin-pwa** generates the manifest and a Workbox service worker, so the
  app is installable and its shell loads offline. `/api` is excluded from the
  service worker so data is never stale.
- **Icons are generated by a stdlib-only Python script** (`scripts/make_icons.py`)
  so there's no image-editing dependency; includes a maskable icon for Android.
- **Mobile-first single page with a bottom tab bar**; light and dark themes via
  CSS variables and `prefers-color-scheme`. Chart colors come from a
  colorblind-validated reference palette; the weight chart shows raw weigh-ins as
  muted dots and the trend as a blue line, with a legend and hover tooltips.
- **Weekly check-in runs automatically** when the app opens and one is due; the
  Trends tab can also force one.
- **Metric units only** for now (kg, cm). Imperial input would be a UI-only change.
