import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["GEMINI_API_KEY"] = ""  # tests always exercise the rule-based path
os.environ["STATIC_DIR"] = str(Path(__file__).resolve().parent / "_no_static")


def make_air_payload(pm25_curve=None, hours=96, start_day=18):
    """Fake Open-Meteo air-quality response: 4 days of hourly data, 'now' = day 2, 14:00."""
    times = [f"2026-11-{start_day + h // 24:02d}T{h % 24:02d}:00" for h in range(hours)]
    if pm25_curve is None:
        # Dirty mornings/evenings, cleaner afternoons, like winter smog.
        pm25_curve = [180 if (h % 24) in (6, 7, 8, 19, 20, 21) else 60 if 12 <= (h % 24) <= 16 else 110 for h in range(hours)]
    return {
        "latitude": 28.6, "longitude": 77.2, "timezone": "Asia/Kolkata",
        "current": {"time": times[38], "us_aqi": 170, "pm2_5": pm25_curve[38], "pm10": 150,
                    "nitrogen_dioxide": 40, "sulphur_dioxide": 10, "ozone": 50, "carbon_monoxide": 1200},
        "hourly": {
            "time": times,
            "pm2_5": pm25_curve,
            "pm10": [v * 1.6 for v in pm25_curve],
            "nitrogen_dioxide": [45.0] * hours,
            "sulphur_dioxide": [12.0] * hours,
            "ozone": [40.0] * hours,
            "carbon_monoxide": [1300.0] * hours,
            "us_aqi": [170] * hours,
        },
    }


def make_weather_payload(hours=96, start_day=18):
    times = [f"2026-11-{start_day + h // 24:02d}T{h % 24:02d}:00" for h in range(hours)]
    return {"hourly": {"time": times, "temperature_2m": [12.0] * hours, "relative_humidity_2m": [88] * hours,
                       "wind_speed_10m": [3.0] * hours, "boundary_layer_height": [250.0] * hours}}


def mock_transport(fail_air=False):
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host.startswith("air-quality-api"):
            if fail_air:
                return httpx.Response(503)
            if "," in request.url.params.get("latitude", ""):
                n = len(request.url.params["latitude"].split(","))
                return httpx.Response(200, json=[{"current": {"pm2_5": 50 + i, "pm10": 80, "us_aqi": 100}} for i in range(n)])
            return httpx.Response(200, json=make_air_payload())
        if host.startswith("api.open-meteo"):
            return httpx.Response(200, json=make_weather_payload())
        if host.startswith("geocoding-api"):
            return httpx.Response(200, json={"results": [{"name": "Delhi", "admin1": "Delhi", "country": "India",
                                                          "country_code": "IN", "latitude": 28.65, "longitude": 77.23}]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def client_factory():
    from fastapi.testclient import TestClient

    from app import main
    from app.services import air_quality
    from app.services.community import ReportStore

    clients = []

    def factory(fail_air=False):
        air_quality.clear_cache()
        main.general_limiter.reset()
        main.ai_limiter.reset()
        main._confirmed.clear()
        main.app.state.http = httpx.AsyncClient(transport=mock_transport(fail_air))
        main.app.state.store = ReportStore(":memory:")
        c = TestClient(main.app)
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)
    store = getattr(main.app.state, "store", None)
    if store is not None:
        store.close()
    for attr in ("http", "store"):
        if hasattr(main.app.state, attr):
            delattr(main.app.state, attr)


@pytest.fixture
def client(client_factory):
    return client_factory()
