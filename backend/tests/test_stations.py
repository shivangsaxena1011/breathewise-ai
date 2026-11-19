"""Station readings: parsing, safety checks, unit conversion and model calibration."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.services import air_quality, stations
from app.services.air_quality import _best_windows, build_snapshot
from tests.conftest import make_air_payload, make_weather_payload

NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)  # = 15:00 IST, the fake "now" hour


def feed(aqi=190, pm25=190, pm10=152, lat=28.63, lon=77.20, iso="2026-11-19T15:00:00+05:30", status="ok"):
    return {"status": status, "data": {
        "aqi": aqi, "idx": 1, "dominentpol": "pm25",
        "city": {"geo": [lat, lon], "name": "Burari Crossing, Delhi"},
        "iaqi": {"pm25": {"v": pm25}, "pm10": {"v": pm10}, "t": {"v": 25}},
        "time": {"s": "2026-11-19 15:00:00", "tz": "+05:30", "iso": iso},
        "attributions": [{"name": "CPCB - India Central Pollution Control Board", "url": "http://cpcb.nic.in/"},
                         {"name": "World Air Quality Index Project", "url": "https://waqi.info/"}],
    }}


@pytest.mark.parametrize("index,conc", [(0, 0.0), (50, 12.0), (100, 35.4), (150, 55.4), (200, 150.4), (500, 500.4)])
def test_us_aqi_to_concentration_breakpoints(index, conc):
    assert stations.aqi_to_concentration(index, stations.US_PM25) == conc


def test_us_aqi_to_concentration_inside_band():
    # 190 sits in the 151-200 band → 55.5 + (39/49) × 94.9 ≈ 131 µg/m³
    assert stations.aqi_to_concentration(190, stations.US_PM25) == pytest.approx(131.0, abs=0.2)
    assert stations.aqi_to_concentration(None, stations.US_PM25) is None
    assert stations.aqi_to_concentration(900, stations.US_PM25) == 500.4


def test_parse_valid_feed():
    st = stations.parse_feed(feed(), 28.61, 77.21, now=NOW)
    assert st["name"].startswith("Burari") and st["us_aqi"] == 190
    assert 1 < st["distance_km"] < 5 and st["age_minutes"] == 0
    assert st["pm25"] == pytest.approx(131.0, abs=0.2)
    assert any("World Air Quality Index" in a["name"] for a in st["attributions"])


@pytest.mark.parametrize("payload", [
    {"status": "error", "data": "Invalid key"},
    feed(aqi="-"),                                   # station offline
    feed(lat=29.5, lon=78.5),                        # > 30 km away
    feed(iso="2026-11-19T08:00:00+05:30"),           # 7 h old
    feed(iso="not-a-time"),
    {"status": "ok", "data": "unexpected"},
    None,
])
def test_parse_rejects_unusable_readings(payload):
    assert stations.parse_feed(payload, 28.61, 77.21, now=NOW) is None


def test_calibration_raises_model_to_station_level():
    model = build_snapshot(make_air_payload([40.0] * 96), make_weather_payload())
    model["location"]["utc_offset_seconds"] = 19800
    st = stations.parse_feed(feed(pm25=150, pm10=100), 28.61, 77.21, now=NOW)  # 150 → 55.4 µg/m³
    snap = stations.apply_station(model, st, _best_windows)
    f = snap["station"]["calibration"]["pm2_5"]
    assert f == pytest.approx(55.4 / 40.0, rel=0.01)
    assert snap["hourly"][snap["now_index"]]["pm2_5"] == pytest.approx(55.4, rel=0.01)
    assert snap["hourly"][0]["pm2_5_model"] == 40.0
    assert snap["aqi"]["basis"] == "station_calibrated"
    assert snap["aqi"]["value"] > model["aqi"]["value"]
    assert model["aqi"].get("basis") == "model"  # original untouched (pure function)


def test_calibration_is_clamped():
    model = build_snapshot(make_air_payload([10.0] * 96), None)
    model["location"]["utc_offset_seconds"] = 19800
    st = stations.parse_feed(feed(pm25=400), 28.61, 77.21, now=NOW)  # ~400 µg/m³ vs model 10
    snap = stations.apply_station(model, st)
    assert snap["station"]["calibration"]["pm2_5"] == stations.BIAS_MAX


def test_no_calibration_when_model_too_low():
    model = build_snapshot(make_air_payload([2.0] * 96), None)
    model["location"]["utc_offset_seconds"] = 19800
    st = stations.parse_feed(feed(), 28.61, 77.21, now=NOW)
    snap = stations.apply_station(model, st)
    assert snap["station"]["calibration"]["pm2_5"] is None
    assert snap["aqi"]["value"] == model["aqi"]["value"]


def test_no_station_returns_model_unchanged():
    model = build_snapshot(make_air_payload(), None)
    assert stations.apply_station(model, None) is model


def test_lookup_without_token_skips_network():
    def boom(request):  # pragma: no cover - must not be called
        raise AssertionError("network used without a token")
    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    import asyncio
    assert asyncio.run(stations.nearest_station(client, 28.6, 77.2, token="")) is None


def test_lookup_survives_errors_and_bad_keys():
    import asyncio

    def handler(request):
        return httpx.Response(200, json={"status": "error", "data": "Invalid key"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(stations.nearest_station(client, 28.6, 77.2, token="bad")) is None

    def down(request):
        return httpx.Response(503)
    client = httpx.AsyncClient(transport=httpx.MockTransport(down))
    assert asyncio.run(stations.nearest_station(client, 28.6, 77.2, token="t")) is None


def test_api_snapshot_includes_station_when_configured(client, monkeypatch):
    now_iso = (datetime.now(UTC) - timedelta(minutes=20)).astimezone().isoformat(timespec="seconds")

    async def fake_nearest(http, lat, lon, token=None):
        return stations.parse_feed(feed(iso=now_iso), lat, lon)

    monkeypatch.setattr(air_quality.stations, "nearest_station", fake_nearest)
    body = client.get("/api/air", params={"lat": 28.61, "lon": 77.21}).json()
    assert body["station"]["name"].startswith("Burari")
    assert body["station"]["attributions"]


def test_api_snapshot_without_station(client):
    body = client.get("/api/air", params={"lat": 28.61, "lon": 77.21}).json()
    assert body["station"] is None and body["aqi"]["basis"] == "model"
