"""Scenario tests: every engine across clean, moderate and severe air, in both languages,
plus the app-wiring paths (SPA serving, store selection, client IP, rate limiting)."""

import dataclasses

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import main
from app.schemas import Activity, Home, Household, Member, Room
from app.services import assistant, cache, exposure, indoor, planner, risk
from app.services.air_quality import build_snapshot
from app.services.community import RedisReportStore, SQLiteReportStore
from tests.conftest import make_air_payload, make_weather_payload

HOURS = 96
NOW = "2026-11-19T14:00"  # make_air_payload's "current" hour


def flat_snapshot(pm25: float):
    return build_snapshot(make_air_payload([pm25] * HOURS), make_weather_payload())


AIR = {"clean": flat_snapshot(8), "moderate": flat_snapshot(70), "severe": flat_snapshot(300)}

EVERYTHING_HOUSEHOLD = Household(
    members=[
        Member(name="Asha", age_group="adult", outdoor_hours=6, commute_mode="two_wheeler", exercises_outdoors=True),
        Member(name="Dadi", age_group="elderly", conditions=["copd", "heart"]),
        Member(name="Meera", age_group="adult", conditions=["pregnant"], commute_mode="walk"),
        Member(name="Kabir", age_group="child", conditions=["asthma"]),
        Member(name="Baby", age_group="infant"),
    ],
    home=Home(has_purifier=False, cooking_fuel="biomass", smoker_at_home=True, burns_incense=True, has_pets=True),
)


# ----------------------------------------------------------------------------- engines x air x language
@pytest.mark.parametrize("air", AIR)
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_family_plan_covers_every_member_with_reasons(air, lang):
    plan = risk.build_plan(EVERYTHING_HOUSEHOLD, AIR[air], lang)
    assert [m["name"] for m in plan["members"]] == [m.name for m in EVERYTHING_HOUSEHOLD.members]
    for member in plan["members"]:
        if air != "clean":  # on clean days a low-risk member may simply have nothing to change
            assert member["actions"], member["name"]
        assert all(a["text"] and a["why"] for a in member["actions"])
    assert plan["household_actions"]
    assert plan["most_at_risk"] in {"Dadi", "Kabir", "Baby", "Meera"}


def test_plan_escalates_with_pollution():
    clean = risk.build_plan(EVERYTHING_HOUSEHOLD, AIR["clean"])
    severe = risk.build_plan(EVERYTHING_HOUSEHOLD, AIR["severe"])
    assert clean["air_level"] < severe["air_level"]
    severe_texts = " ".join(a["text"] for m in severe["members"] for a in m["actions"])
    assert "indoors" in severe_texts
    clean_texts = " ".join(a["text"] for m in clean["members"] for a in m["actions"])
    assert "fine" in clean_texts


@pytest.mark.parametrize("air", AIR)
@pytest.mark.parametrize("purifier", [True, False])
def test_indoor_doctor_verdicts(air, purifier):
    home = Home(has_purifier=purifier, cooking_fuel="kerosene", smoker_at_home=True, has_pets=True)
    rooms = [Room(kind=k) for k in ("kitchen", "bedroom", "living", "kids", "study", "bathroom")]
    result = indoor.diagnose(home, rooms, AIR[air], "en")
    assert result["ventilation"]["verdict"] == {"clean": "open", "moderate": "brief", "severe": "closed"}[air]
    assert len(result["rooms"]) == len(rooms)
    assert result["general"]
    hi = indoor.diagnose(home, rooms, AIR[air], "hi")
    assert hi["ventilation"]["verdict"] == result["ventilation"]["verdict"]


def test_indoor_brief_airing_when_now_is_cleaner_than_the_day():
    curve = [300.0] * HOURS
    curve[38] = 8.0  # one clean hour right now inside a smoggy day
    snap = build_snapshot(make_air_payload(curve), make_weather_payload())
    assert indoor.diagnose(Home(), [Room(kind="living")], snap, "en")["ventilation"]["verdict"] in {"brief", "closed"}


@pytest.mark.parametrize("air", AIR)
@pytest.mark.parametrize("commute", ["car_petrol", "metro", None])
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_routine_for_every_commute(air, commute, lang):
    steps = planner.routine(EVERYTHING_HOUSEHOLD, AIR[air], commute, lang)["steps"]
    times = [s["time"] for s in steps]
    assert times == sorted(times)
    assert any(s["title"] in {"Commute", "आना-जाना"} for s in steps)


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_alerts_cover_past_ok_and_warn(lang):
    activities = [
        Activity(title="Old walk", start="2026-11-18T07:00"),  # already passed
        Activity(title="Picnic", start="2026-11-20T13:00", sensitive=True),
        Activity(title="Out of range", start="2026-12-30T07:00"),
    ]
    clean = planner.alerts(activities, AIR["clean"], EVERYTHING_HOUSEHOLD, lang)["alerts"]
    assert [a["status"] for a in clean] == ["unknown", "ok", "unknown"]
    severe = planner.alerts(activities, AIR["severe"], None, lang)["alerts"]
    assert severe[1]["status"] == "warn" and "suggested_time" not in severe[1]


def test_exercise_shift_unavailable_without_forecast():
    snap = dict(AIR["clean"], hourly=[], now_index=0)
    assert exposure.exercise_shift(snap, 7, 45, "moderate") == {"available": False}
    no_daytime = dict(AIR["clean"], hourly=[dict(h, pm2_5=None) for h in AIR["clean"]["hourly"]])
    assert exposure.exercise_shift(no_daytime, 7, 45, "light") == {"available": False}


@pytest.mark.parametrize("level", range(6))
def test_rule_based_lines_exist_for_every_level(level):
    for lang in ("en", "hi"):
        assert assistant._exercise_line(level, lang)
        assert assistant._kids_line(level, lang)


@pytest.mark.parametrize("message", ["run", "kids", "home", "mask", "metro", "hello"])
def test_hindi_fallback_for_every_topic(message):
    reply = assistant.fallback_answer(message, AIR["moderate"], "hi")
    assert reply and "{" not in reply


# ----------------------------------------------------------------------------- cache & rate limiter
def test_ttl_cache_expires_and_evicts(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    c = cache.TTLCache(ttl_seconds=10, max_items=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)  # evicts the least recently used key
    assert c.get("a") is None and c.get("c") == 3
    now[0] += 11
    assert c.get("b") is None


def test_rate_limiter_window_and_key_eviction(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    limiter = cache.RateLimiter(limit=1, window=60, max_keys=2)
    assert limiter.allow("x") and not limiter.allow("x")
    now[0] += 61
    assert limiter.allow("x")
    limiter.allow("y")
    limiter.allow("z")  # evicts the oldest key rather than growing without bound
    assert len(limiter._hits) == 2


# ----------------------------------------------------------------------------- app wiring
def test_spa_serves_files_and_falls_back_to_index(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<!doctype html><title>BreatheWise</title>")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path.parent / "secret.txt").write_text("nope")
    app = FastAPI()
    assert main.mount_spa(app, tmp_path)
    with TestClient(app) as c:
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/logo.png").content.startswith(b"\x89PNG")
        index = c.get("/family")
        assert "BreatheWise" in index.text and index.headers["cache-control"] == "no-cache"
        assert "nope" not in c.get("/../secret.txt").text
        assert c.get("/api/unknown").status_code == 404


def test_spa_not_mounted_without_a_build(tmp_path):
    assert main.mount_spa(FastAPI(), tmp_path) is False


def test_store_uses_redis_when_configured(monkeypatch):
    app = FastAPI()
    app.state.http = httpx.AsyncClient()
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, redis_url="https://r.example", redis_token="t"))
    assert isinstance(main.get_store(app), RedisReportStore)
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, redis_url="", redis_token=""))
    app.state.store = None
    store = main.get_store(app)
    assert isinstance(store, SQLiteReportStore)
    store.close()


@pytest.mark.parametrize(
    ("on_vercel", "headers", "expected"),
    [
        (True, {"x-vercel-forwarded-for": "1.1.1.1, 9.9.9.9"}, "1.1.1.1"),
        (True, {"x-real-ip": "2.2.2.2"}, "2.2.2.2"),
        (False, {"x-vercel-forwarded-for": "6.6.6.6", "x-forwarded-for": "6.6.6.6, 3.3.3.3"}, "3.3.3.3"),
        (False, {}, "testclient"),
    ],
)
def test_client_ip_trusts_only_platform_headers(monkeypatch, on_vercel, headers, expected):
    monkeypatch.setattr(main, "ON_VERCEL", on_vercel)
    app = FastAPI()

    @app.get("/ip")
    def ip(request: main.Request) -> dict[str, str]:
        return {"ip": main.client_ip(request)}

    with TestClient(app) as c:
        assert c.get("/ip", headers=headers).json()["ip"] == expected


def test_rate_limited_response_still_has_security_headers(client, monkeypatch):
    monkeypatch.setattr(main, "general_limiter", cache.RateLimiter(limit=1))
    assert client.get("/api/air", params={"lat": 28.6, "lon": 77.2}).status_code == 200
    blocked = client.get("/api/air", params={"lat": 28.6, "lon": 77.2})
    assert blocked.status_code == 429
    assert blocked.headers["x-frame-options"] == "DENY"
    assert "max-age" in blocked.headers["strict-transport-security"]


def test_health_and_docs_are_not_rate_limited(client, monkeypatch):
    monkeypatch.setattr(main, "general_limiter", cache.RateLimiter(limit=0))
    assert client.get("/api/health").status_code == 200
    docs = client.get("/api/docs")
    assert docs.status_code == 200 and "content-security-policy" not in docs.headers


def test_whatif_exercise_degrades_when_forecast_fails(client_factory):
    c = client_factory(fail_air=True)
    body = {"lat": 28.6, "lon": 77.2, "exercise_shift": {"current_hour": 7}}
    result = c.post("/api/whatif", json=body).json()["results"]["exercise_shift"]
    assert result == {"available": False, "reason": "Forecast unavailable right now."}


def test_chat_without_data_never_states_an_aqi(client_factory):
    c = client_factory(fail_air=True)
    reply = c.post("/api/chat", json={"message": "Can I run?", "lat": 28.6, "lon": 77.2}).json()
    assert reply["mode"] == "rules" and "won't guess" in reply["reply"]


def test_unknown_report_cannot_be_confirmed(client):
    assert client.post("/api/reports/9999/confirm").status_code == 404


def test_snapshot_hour_matches_fixture():
    assert AIR["clean"]["observed_at"] == NOW


# ----------------------------------------------------------------------------- data edge cases
def test_window_mean_needs_two_thirds_coverage():
    from app.services.air_quality import _window_mean

    assert _window_mean([None] * 20 + [50.0] * 4, 23, 24) is None
    assert _window_mean([50.0] * 24, 23, 24) == 50.0


def test_current_index_matches_on_the_hour_or_falls_back():
    from app.services.air_quality import _current_index

    times = ["2026-11-19T13:00", "2026-11-19T14:00"]
    assert _current_index(times, "2026-11-19T14:15") == 1
    assert _current_index(["2999-01-01T00:00"], None) == 0  # nothing in the past yet


def test_snapshot_without_weather_or_current_block():
    payload = make_air_payload()
    payload.pop("current")
    snap = build_snapshot(payload, None)
    assert snap["weather_now"]["wind_speed_10m"] is None and snap["smog_drivers"] == []
    assert all(v is None for v in snap["pollutants_now"].values())


def test_air_survives_weather_outage_and_caches(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host.startswith("api.open-meteo"):
            return httpx.Response(503)
        if "," in request.url.params.get("latitude", ""):
            return httpx.Response(200, json=[{"current": {"pm2_5": 40}}] * 25)
        if request.url.host.startswith("geocoding-api"):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json=make_air_payload())

    c = client_factory()
    main.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    loc = {"lat": 28.6, "lon": 77.2}
    first = c.get("/api/air", params=loc).json()
    assert first["aqi"]["value"] and first["weather_now"]["temperature_2m"] is None
    assert c.get("/api/air", params=loc).json() == first  # served from cache
    assert c.get("/api/air/grid", params=loc).json() == c.get("/api/air/grid", params=loc).json()
    assert c.get("/api/geocode", params={"q": "Nowhere"}).json() == {"results": []}
    assert c.get("/api/geocode", params={"q": "Nowhere"}).json() == {"results": []}


def test_http_client_is_created_lazily():
    app = FastAPI()
    client = main.get_http(app)
    assert client is main.get_http(app)


# ----------------------------------------------------------------------------- photo endpoint guards
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32


def test_photo_sniffing():
    assert main.sniff_image(WEBP) == "image/webp"
    assert main.sniff_image(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert main.sniff_image(b"GIF89a") is None


def test_photo_too_large(client):
    big = b"\xff\xd8\xff" + b"\x00" * main.MAX_UPLOAD_BYTES
    r = client.post("/api/reports/analyze", files={"photo": ("a.jpg", big, "image/jpeg")})
    assert r.status_code == 413


def test_photo_ai_failure_and_success(client, monkeypatch):
    monkeypatch.setattr(main.gemini, "enabled", lambda: True)

    async def failing(*_args):
        return None

    monkeypatch.setattr(main.assistant, "analyse_photo", failing)
    files = {"photo": ("a.webp", WEBP, "image/webp")}
    assert client.post("/api/reports/analyze", files=files).status_code == 503

    async def ok(*_args):
        return {"category": "waste_burning", "visible_signs": ["smoke"], "severity": "high",
                "suggested_description": "Burning garbage", "confidence": "high"}

    monkeypatch.setattr(main.assistant, "analyse_photo", ok)
    body = client.post("/api/reports/analyze", files=files).json()
    assert body["category"] == "waste_burning" and "not stored" in body["note"]


def test_whatif_exercise_needs_location(client):
    r = client.post("/api/whatif", json={"exercise_shift": {"current_hour": 7}})
    assert r.status_code == 422


# ----------------------------------------------------------------------------- AI paths with a fake model
@pytest.fixture
def fake_ai(monkeypatch):
    calls = []

    async def gen_json(system, contents, schema, *, max_tokens=0):
        calls.append(("json", system, contents))
        return {"ok": True}

    async def gen_text(system, contents, *, max_tokens=0):
        calls.append(("text", system, contents))
        return "Explained."

    monkeypatch.setattr(assistant.gemini, "enabled", lambda: True)
    monkeypatch.setattr(assistant.gemini, "generate_json", gen_json)
    monkeypatch.setattr(assistant.gemini, "generate_text", gen_text)
    return calls


def test_ai_features_wrap_user_data(fake_ai):
    import asyncio

    plan = risk.build_plan(EVERYTHING_HOUSEHOLD, AIR["severe"], "hi")
    assert asyncio.run(assistant.personalise_plan(plan, "hi")) == {"ok": True}
    assert asyncio.run(assistant.analyse_photo(b"img", "image/png", "en")) == {"ok": True}
    assert asyncio.run(assistant.explain_what_if({"energy_saving": {"kg": 1}}, "en")) == "Explained."
    prompts = [c[2] for c in fake_ai if isinstance(c[2], str)]
    assert all("<USER_DATA>" in p and "</USER_DATA>" in p for p in prompts)
    assert "Hindi" in fake_ai[0][1]


# ----------------------------------------------------------------------------- configuration secrets
def test_voter_salt_is_never_a_public_default(monkeypatch):
    from app import config

    for var in ("VOTER_SALT", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_TOKEN", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert config._voter_salt() != config._voter_salt()  # random per process when no secret exists
    monkeypatch.setenv("KV_REST_API_TOKEN", "shared-secret")
    assert config._voter_salt() == config._voter_salt()  # stable across serverless instances
    assert "shared-secret" not in config._voter_salt()
    monkeypatch.setenv("VOTER_SALT", "explicit")
    assert config._voter_salt() == "explicit"


def test_secrets_are_hidden_from_settings_repr(monkeypatch):
    from app import config

    monkeypatch.setenv("GEMINI_API_KEY", "sk-very-secret")
    monkeypatch.setenv("WAQI_TOKEN", "waqi-secret")
    text = repr(config.Settings())
    assert "sk-very-secret" not in text and "waqi-secret" not in text
