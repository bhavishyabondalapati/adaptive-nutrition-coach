from datetime import timedelta

from app.calculations import KCAL_PER_KG
from tests.conftest import TODAY

PROFILE = {
    "sex": "male", "age": 30, "height_cm": 180, "weight_kg": 80,
    "activity_level": "moderate", "goal": "cut", "training_days": 4, "equipment": "dumbbells",
}


def setup_profile(client):
    assert client.put("/api/profile", json=PROFILE).status_code == 200


def test_health(client):
    assert client.get("/api/health").json()["parser"] == "rule-based"


def test_targets_need_profile(client):
    assert client.get("/api/targets").status_code == 404


def test_profile_validation(client):
    assert client.put("/api/profile", json={**PROFILE, "age": 5}).status_code == 422
    assert client.put("/api/profile", json={**PROFILE, "goal": "shred"}).status_code == 422


def test_formula_targets(client):
    setup_profile(client)
    data = client.get("/api/targets").json()
    assert data["formula_tdee"] == 2759  # 1780 BMR x 1.55
    assert data["tdee_source"] == "formula"
    assert data["targets"]["calories"] == 2759 - 440
    assert data["checkin_due"] is True


def test_log_food_and_daily_intake(client):
    r = client.post("/api/food", json={"text": "2 eggs and 1 slice toast"}).json()
    assert [i["matched_name"] for i in r["items"]] == ["egg", "toast"]
    assert client.get("/api/food").json()[0]["kcal"] == 143
    today = client.get("/api/intake?days=7").json()[-1]
    assert today["day"] == TODAY.isoformat()
    assert today["kcal"] == round(143 + 265 * 0.3)


def test_parse_preview_does_not_save(client):
    client.post("/api/food/parse", json={"text": "1 banana"})
    assert client.get("/api/food").json() == []


def test_delete_food(client):
    item = client.post("/api/food", json={"text": "1 apple"}).json()["items"][0]
    assert client.delete(f"/api/food/{item['id']}").status_code == 200
    assert client.get("/api/food").json() == []


def test_weight_upsert_and_trend(client):
    client.post("/api/weights", json={"weight_kg": 80})
    client.post("/api/weights", json={"weight_kg": 79})  # same day: replaces
    rows = client.get("/api/weights").json()
    assert len(rows) == 1 and rows[0]["weight_kg"] == 79 and rows[0]["trend_kg"] == 79


def test_workout_plan_uses_profile(client):
    setup_profile(client)
    plan = client.get("/api/workout-plan").json()
    assert plan["days_per_week"] == 4 and plan["equipment"] == "dumbbells"
    assert client.get("/api/workout-plan?days=6").json()["split"].startswith("Push")


def test_checkin_flow_adapts_targets(client):
    setup_profile(client)
    # 5 weeks eating ~2000 kcal/day with a real TDEE of 2300.
    intake = 9.75 * 158 * 1.30  # 9.75 cups of rice (158 g/cup, 130 kcal/100 g) = 2003 kcal
    kg = 80.0
    for i in range(35, 0, -1):
        day = (TODAY - timedelta(days=i - 1)).isoformat()
        client.post("/api/weights", json={"day": day, "weight_kg": round(kg, 2)})
        client.post("/api/food", json={"day": day, "text": "9.75 cup rice"})
        kg += (intake - 2300) / KCAL_PER_KG  # energy balance

    first = client.post("/api/checkins").json()
    assert first["checkin"]["status"] == "ok"
    # Within 60 kcal: the EWMA trend is still warming up after only 5 weeks of data.
    assert abs(first["estimate"]["raw_estimate"] - 2300) < 60
    # Formula said ~2750; change limited to 200 kcal this week.
    assert first["checkin"]["used_tdee"] == first["checkin"]["formula_tdee"] - 200

    # Not due again until a week later.
    assert client.post("/api/checkins").status_code == 409
    assert client.post("/api/checkins?force=true").status_code == 200

    targets = client.get("/api/targets").json()
    assert targets["tdee_source"] == "adaptive"
    assert targets["checkin_due"] is False
    assert len(client.get("/api/checkins").json()) == 2


def test_checkin_with_no_data_keeps_formula(client):
    setup_profile(client)
    r = client.post("/api/checkins").json()
    assert r["checkin"]["status"] == "insufficient_data"
    assert client.get("/api/targets").json()["tdee_source"] == "formula"
