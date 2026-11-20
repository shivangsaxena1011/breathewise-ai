"""Targeted tests to achieve 100% test coverage across all backend services."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, Request

from app import main as main_mod
from app.schemas import Home, Household, Member, ReportCreate
from app.services import air_quality, aqi, assistant, community, exposure, gemini, risk, stations


def run(coro):
    return asyncio.run(coro)


def test_schemas_description_too_short():
    with pytest.raises(ValueError, match="Description too short"):
        ReportCreate(category="smoke", description="   hi   ", lat=28.6, lon=77.2)


def test_air_quality_empty_window():
    assert air_quality._window([], "empty") is None
    hours = [
        {"time": "2026-11-20T08:00", "pm2_5": 50.0},
        {"time": "2026-11-20T12:00", "pm2_5": 60.0},
    ]
    assert air_quality._window(hours, "sparse") is None


def test_aqi_pm25_level_none():
    assert aqi.pm25_level(None) == 0


def test_assistant_disabled_gemini(monkeypatch):
    monkeypatch.setattr(gemini, "enabled", lambda: False)
    assert run(assistant.analyse_photo(b"fake", "image/jpeg", "en")) is None
    assert run(assistant.explain_what_if({"test": 1}, "en")) is None


def test_community_redis_edge_cases():
    # 1. Pipeline error branch
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/pipeline"):
            return httpx.Response(200, json=[{"error": "ERR syntax error"}])
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    store = community.RedisReportStore("https://example.upstash.io", "token", client)
    with pytest.raises(community.StoreError, match="Report database rejected the request"):
        run(store._pipeline(["SOME", "CMD"]))

    # 2. Empty nearby results
    async def empty_nearby_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"result": []}])

    client2 = httpx.AsyncClient(transport=httpx.MockTransport(empty_nearby_handler))
    store2 = community.RedisReportStore("https://example.upstash.io", "token", client2)
    assert run(store2.nearby(28.6, 77.2)) == []

    # 3. Expired nearby reports cleaned up
    pipe_calls = []

    async def expired_nearby_handler(request: httpx.Request) -> httpx.Response:
        pipe_calls.append(request.read())
        if len(pipe_calls) == 1:
            return httpx.Response(200, json=[{"result": ["1", "2"]}])
        if len(pipe_calls) == 2:
            row = [
                "id", "1", "category", "smoke", "description", "valid description",
                "lat", "28.6", "lon", "77.2", "created_at", "10000000000",
                "confirmations", "0", "ai_assisted", "0",
            ]
            return httpx.Response(200, json=[{"result": row}, {"result": []}])
        return httpx.Response(200, json=[{"result": 1}])

    client3 = httpx.AsyncClient(transport=httpx.MockTransport(expired_nearby_handler))
    store3 = community.RedisReportStore("https://example.upstash.io", "token", client3)
    res = run(store3.nearby(28.6, 77.2))
    assert len(res) == 1
    assert res[0]["id"] == 1


def test_exposure_missing_pm():
    snapshot = {
        "now_index": 0,
        "hourly": [
            {"time": "2026-11-20T08:00", "pm2_5": None},
            {"time": "2026-11-20T09:00", "pm2_5": 50.0},
        ]
    }
    res = exposure.exercise_shift(snapshot, 8, 60, "moderate")
    assert res == {"available": False}


def test_stations_nearest_station_success():
    now_iso = datetime.now(UTC).isoformat()
    mock_payload = {
        "status": "ok",
        "data": {
            "aqi": 120,
            "idx": 1234,
            "dominentpol": "pm25",
            "city": {"geo": [28.61, 77.21], "name": "Delhi Test Station"},
            "iaqi": {"pm25": {"v": 120}},
            "time": {"iso": now_iso},
            "attributions": [{"name": "CPCB", "url": "http://cpcb.nic.in/"}],
        }
    }
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    st = run(stations.nearest_station(client, 28.61, 77.21, token="valid-token"))
    assert st is not None
    assert st["name"] == "Delhi Test Station"


def test_gemini_none_client_and_generate_json(monkeypatch):
    monkeypatch.setattr(gemini, "_get_client", lambda: None)
    assert run(gemini._generate(["test"], None)) is None
    assert run(gemini.generate_json("system", "content", {})) is None


def test_gemini_get_client(monkeypatch):
    new_settings = dataclasses.replace(gemini.settings, gemini_api_key="test-key-12345")
    monkeypatch.setattr(gemini, "settings", new_settings)
    monkeypatch.setattr(gemini._state, "client", None)
    client1 = gemini._get_client()
    assert client1 is not None
    # Test second call when client already exists (branch 54->58)
    client2 = gemini._get_client()
    assert client2 is client1


def test_air_quality_current_index_mismatch_fallback():
    times = ["2026-11-20T08:00"]
    # Prefix "2026-11-20T15" does not match any entry in times, falls back to local_now search
    idx = air_quality._current_index(times, "2026-11-20T15:30:00", utc_offset_seconds=19800)
    assert idx == 0


def test_main_client_ip_vercel_fallback(monkeypatch):
    monkeypatch.setattr(main_mod, "ON_VERCEL", True)

    req = Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-forwarded-for", b"203.0.113.195")],
    })
    assert main_mod.client_ip(req) == "203.0.113.195"


def test_main_mount_static_no_assets(tmp_path):
    app_test = FastAPI()
    (tmp_path / "index.html").write_text("<html></html>")
    # Assets directory is absent
    assert main_mod.mount_spa(app_test, tmp_path) is True


def test_stations_apply_partial_pollutants():
    snapshot = {
        "location": {"utc_offset_seconds": 19800},
        "now_index": 0,
        "hourly": [
            {"time": "2026-11-20T12:00", "pm2_5": 50.0, "pm10": 100.0},
            {"time": "2026-11-20T13:00", "pm2_5": None, "pm10": None},
        ],
        "averages": {},
        "pollutants_now": {},
        "aqi": {"value": 50, "label": "Good", "level": 1, "color": "#00e400"},
        "source": "model",
    }
    station = {
        "name": "Station Y",
        "distance_km": 5.0,
        "age_minutes": 10,
        "us_aqi": 100,
        "measured_at": "2026-11-20T12:00:00+05:30",
        "attributions": [],
        "pm25": 100.0,
        "pm10": 200.0,
    }
    snap = stations.apply_station(snapshot, station)
    assert snap["hourly"][0]["pm2_5"] == 100.0
    assert snap["hourly"][1]["pm2_5"] is None


def test_main_lifespan_store_none():
    async def run_lifespan_test():
        app_test = FastAPI()
        async with main_mod.lifespan(app_test):
            app_test.state.store = None
        assert app_test.state.http is None

    run(run_lifespan_test())


def test_risk_with_purifier():
    h = Household(
        members=[Member(name="A", age_group="adult", conditions=[], outdoor_hours=1, exercises_outdoors=False)],
        home=Home(has_purifier=True, cooking_fuel="lpg", smoker_at_home=False, burns_incense=False, has_pets=False)
    )
    actions = risk.household_actions(h, 4, "2026-11-20T12:00", "2026-11-20T04:00", "en")
    assert any("purifier" in a["text"].lower() for a in actions)
