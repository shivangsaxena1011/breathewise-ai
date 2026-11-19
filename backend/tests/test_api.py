HOUSEHOLD = {"members": [{"name": "Riya", "age_group": "child", "exercises_outdoors": True},
                         {"name": "Dadi", "age_group": "elderly", "conditions": ["asthma"]}],
             "home": {"has_purifier": False, "cooking_fuel": "lpg"}}
LOC = {"lat": 28.61, "lon": 77.21}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ai"] is False


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_geocode(client):
    r = client.get("/api/geocode", params={"q": "Delhi"})
    assert r.json()["results"][0]["name"] == "Delhi"


def test_geocode_validates_input(client):
    assert client.get("/api/geocode", params={"q": "x"}).status_code == 422


def test_air_snapshot(client):
    body = client.get("/api/air", params=LOC).json()
    assert body["aqi"]["value"] > 0 and body["source"]["kind"] == "model_estimate"


def test_air_rejects_bad_coords(client):
    assert client.get("/api/air", params={"lat": 200, "lon": 0}).status_code == 422


def test_upstream_failure_is_502(client_factory):
    c = client_factory(fail_air=True)
    assert c.get("/api/air", params=LOC).status_code == 502


def test_grid(client):
    assert len(client.get("/api/air/grid", params=LOC).json()["cells"]) == 25


def test_family_plan_without_ai(client):
    body = client.post("/api/plan/family", json={**LOC, "household": HOUSEHOLD}).json()
    assert body["ai"] is None and len(body["members"]) == 2
    assert body["most_at_risk"] == "Dadi"


def test_family_plan_validation(client):
    bad = {**LOC, "household": {"members": []}}
    assert client.post("/api/plan/family", json=bad).status_code == 422


def test_chat_falls_back_to_rules(client):
    body = client.post("/api/chat", json={"message": "Can I go for a run?", **LOC, "lang": "en"}).json()
    assert body["mode"] == "rules" and "AQI" in body["reply"]


def test_chat_rejects_long_message(client):
    assert client.post("/api/chat", json={"message": "x" * 1001}).status_code == 422


def test_indoor_and_routine(client):
    assert "ventilation" in client.post("/api/indoor", json={**LOC, "rooms": [{"kind": "kitchen"}]}).json()
    assert client.post("/api/routine", json={**LOC, "household": HOUSEHOLD}).json()["steps"]


def test_mobility(client):
    rows = client.post("/api/mobility", json={"distance_km": 12}).json()["rows"]
    assert rows[0]["kg_co2_per_person"] <= rows[-1]["kg_co2_per_person"]


def test_whatif_all_scenarios(client):
    body = client.post("/api/whatif", json={
        **LOC,
        "mode_shift": {"from_mode": "car_petrol", "to_mode": "bus", "distance_km_one_way": 8, "days_per_week": 3},
        "exercise_shift": {"current_hour": 19, "duration_min": 45},
        "waste_burning": {"kg_per_week": 1},
        "energy_saving": {"kwh_per_month": 30},
    }).json()
    assert set(body["results"]) == {"mode_shift", "exercise_shift", "waste_burning", "energy_saving"}
    assert "disclaimer" in body


def test_whatif_requires_a_scenario(client):
    assert client.post("/api/whatif", json={}).status_code == 422


def test_alerts(client):
    body = client.post("/api/alerts", json={**LOC, "activities": [
        {"title": "Evening walk", "start": "2026-11-19T19:00", "duration_min": 30}]}).json()
    assert body["alerts"][0]["status"] == "warn"


def test_reports_lifecycle_and_privacy(client):
    r = client.post("/api/reports", json={"category": "waste_burning", "description": "Garbage burning near park",
                                          "lat": 28.613456, "lon": 77.209876})
    assert r.status_code == 201
    rep = r.json()
    assert rep["lat"] == 28.613 and rep["status"] == "unverified"
    for i in range(3):  # three different neighbours
        rep = client.post(f"/api/reports/{rep['id']}/confirm", headers={"x-forwarded-for": f"10.0.0.{i}"}).json()
    assert rep["status"] == "confirmed"
    assert len(client.get("/api/reports", params=LOC).json()["reports"]) == 1


def test_reports_block_links(client):
    r = client.post("/api/reports", json={"category": "other", "description": "visit https://spam.example",
                                          "lat": 28.6, "lon": 77.2})
    assert r.status_code == 422


def test_confirm_missing_report(client):
    assert client.post("/api/reports/999/confirm").status_code == 404


def test_photo_upload_validation(client):
    assert client.post("/api/reports/analyze", files={"photo": ("a.txt", b"hello", "text/plain")}).status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    assert client.post("/api/reports/analyze", files={"photo": ("a.png", png, "image/png")}).status_code == 503


def test_rate_limit(client):
    from app import main
    main.general_limiter.limit, old = 3, main.general_limiter.limit
    try:
        codes = [client.get("/api/air", params=LOC).status_code for _ in range(5)]
    finally:
        main.general_limiter.limit = old
    assert codes[-1] == 429


def test_same_person_cannot_confirm_twice(client):
    rep = client.post("/api/reports", json={"category": "other", "description": "Smoke near the bridge",
                                            "lat": 28.6, "lon": 77.2}).json()
    for _ in range(3):
        last = client.post(f"/api/reports/{rep['id']}/confirm", headers={"x-forwarded-for": "10.9.9.9"}).json()
    assert last["confirmations"] == 1


def test_spoofed_forwarded_for_does_not_bypass_rate_limit(client):
    from app import main
    main.general_limiter.limit, old = 3, main.general_limiter.limit
    try:
        codes = [client.get("/api/air", params=LOC, headers={"x-forwarded-for": f"1.2.3.{i}, 9.9.9.9"}).status_code
                 for i in range(5)]
    finally:
        main.general_limiter.limit = old
    assert codes[-1] == 429


def test_chat_without_location_never_claims_air_is_fine(client):
    body = client.post("/api/chat", json={"message": "Can I go jogging?"}).json()
    assert body["mode"] == "rules" and "won't guess" in body["reply"]


def test_vercel_headers_ignored_off_vercel(client):
    from app import main
    main.general_limiter.limit, old = 3, main.general_limiter.limit
    try:
        codes = [client.get("/api/air", params=LOC, headers={"x-vercel-forwarded-for": f"7.7.7.{i}"}).status_code
                 for i in range(5)]
    finally:
        main.general_limiter.limit = old
    assert codes[-1] == 429


def test_whatif_survives_forecast_outage(client_factory):
    c = client_factory(fail_air=True)
    body = c.post("/api/whatif", json={
        **LOC, "mode_shift": {"from_mode": "car_petrol", "to_mode": "bus", "distance_km_one_way": 8, "days_per_week": 3},
        "exercise_shift": {"current_hour": 19}}).json()
    assert body["results"]["mode_shift"]["kg_co2_saved_year"] > 0
    assert body["results"]["exercise_shift"]["available"] is False


def test_past_activity_is_flagged(client):
    body = client.post("/api/alerts", json={**LOC, "activities": [
        {"title": "Morning walk", "start": "2026-11-19T07:00", "duration_min": 30}]}).json()
    assert body["alerts"][0]["status"] == "unknown" and "passed" in body["alerts"][0]["message"]
