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
