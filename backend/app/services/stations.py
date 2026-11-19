"""Live ground-station readings (World Air Quality Index project, which relays CPCB stations in India).

Why: atmospheric models smooth over cities and tend to under-read Indian winter PM peaks. When a
monitoring station is close and recent, we use it to *calibrate* the model: the ratio between the
station's measured PM and the model's value for the same hour corrects both the AQI and the forecast.
The model still provides the hour-by-hour shape and the 3-day outlook that a single station can't.

Without a WAQI token, or with no station within range, everything falls back to the model alone.
"""

from __future__ import annotations

import logging
import math
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ..config import settings
from . import aqi as aqi_math

log = logging.getLogger("breathewise.stations")

WAQI_GEO_URL = "https://api.waqi.info/feed/geo:{lat};{lon}/"
MAX_DISTANCE_KM = 30.0
MAX_AGE_HOURS = 3.0
BIAS_MIN, BIAS_MAX = 0.4, 3.0

# WAQI reports US-EPA AQI sub-indices (it adopted the 2013 PM2.5 breakpoints for all countries).
# (aqi_low, aqi_high, conc_low, conc_high) in µg/m³
US_PM25 = [(0, 50, 0.0, 12.0), (51, 100, 12.1, 35.4), (101, 150, 35.5, 55.4), (151, 200, 55.5, 150.4),
           (201, 300, 150.5, 250.4), (301, 400, 250.5, 350.4), (401, 500, 350.5, 500.4)]
US_PM10 = [(0, 50, 0, 54), (51, 100, 55, 154), (101, 150, 155, 254), (151, 200, 255, 354),
           (201, 300, 355, 424), (301, 400, 425, 504), (401, 500, 505, 604)]


def aqi_to_concentration(index: float | None, table: list[tuple[float, float, float, float]]) -> float | None:
    """Invert a US-EPA sub-index back to a concentration (linear within the band)."""
    if index is None or index < 0:
        return None
    for a_lo, a_hi, c_lo, c_hi in table:
        if index <= a_hi:
            return round(c_lo + (c_hi - c_lo) * (max(index, a_lo) - a_lo) / (a_hi - a_lo), 1)
    return table[-1][3]  # above 500: cap at the top of the scale


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def parse_feed(payload: Any, lat: float, lon: float, now: datetime | None = None) -> dict[str, Any] | None:
    """Validate a WAQI geo-feed response. Returns None unless it is a usable, nearby, recent reading."""
    if not isinstance(payload, dict) or payload.get("status") != "ok" or not isinstance(payload.get("data"), dict):
        return None
    data = payload["data"]
    us_aqi = _num(data.get("aqi"))  # "-" means the station is offline
    geo = (data.get("city") or {}).get("geo") or []
    if us_aqi is None or len(geo) != 2 or _num(geo[0]) is None or _num(geo[1]) is None:
        return None
    distance = haversine_km(lat, lon, float(geo[0]), float(geo[1]))
    if distance > MAX_DISTANCE_KM:
        return None
    try:
        measured = datetime.fromisoformat((data.get("time") or {}).get("iso", ""))
    except ValueError:
        return None
    now = now or datetime.now(UTC)
    age_h = (now - measured).total_seconds() / 3600
    if measured.tzinfo is None or age_h > MAX_AGE_HOURS or age_h < -1:
        return None
    iaqi = data.get("iaqi") or {}
    pm25_aqi = _num((iaqi.get("pm25") or {}).get("v"))
    pm10_aqi = _num((iaqi.get("pm10") or {}).get("v"))
    attributions = [
        {"name": str(a.get("name", ""))[:120], "url": str(a.get("url", ""))[:300]}
        for a in (data.get("attributions") or [])[:6] if isinstance(a, dict) and a.get("name")
    ]
    return {
        "name": str((data.get("city") or {}).get("name") or "Monitoring station")[:120],
        "lat": float(geo[0]),
        "lon": float(geo[1]),
        "distance_km": round(distance, 1),
        "measured_at": measured.isoformat(),
        "age_minutes": max(0, round(age_h * 60)),
        "us_aqi": us_aqi,
        "dominant": data.get("dominentpol"),
        "pm25_us_aqi": pm25_aqi,
        "pm10_us_aqi": pm10_aqi,
        "pm25": aqi_to_concentration(pm25_aqi, US_PM25),
        "pm10": aqi_to_concentration(pm10_aqi, US_PM10),
        "attributions": attributions,
    }


async def nearest_station(client: httpx.AsyncClient, lat: float, lon: float, token: str | None = None) -> dict[str, Any] | None:
    token = settings.waqi_token if token is None else token
    if not token:
        return None
    try:
        resp = await client.get(WAQI_GEO_URL.format(lat=lat, lon=lon), params={"token": token}, timeout=8.0)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Station lookup failed: %s", type(exc).__name__)
        return None
    if isinstance(payload, dict) and payload.get("status") == "error":
        log.warning("Station lookup rejected: %s", str(payload.get("data"))[:80])
        return None
    return parse_feed(payload, lat, lon)


def _local_hour(iso: str, utc_offset_seconds: int) -> str:
    t = datetime.fromisoformat(iso).astimezone(UTC) + timedelta(seconds=utc_offset_seconds)
    return t.strftime("%Y-%m-%dT%H:00")


def _ratio(measured: float | None, modelled: float | None) -> float | None:
    if measured is None or modelled is None or modelled < 5:
        return None  # too little signal to calibrate on
    return round(min(BIAS_MAX, max(BIAS_MIN, measured / modelled)), 2)


def apply_station(snapshot: dict[str, Any], station: dict[str, Any] | None,
                  best_windows: Any = None) -> dict[str, Any]:
    """Return a copy of the model snapshot calibrated to a station reading (pure function)."""
    if not station:
        return snapshot
    snap = deepcopy(snapshot)
    offset = snap["location"].get("utc_offset_seconds") or 0
    target = _local_hour(station["measured_at"], offset)
    hourly = snap["hourly"]
    at = next((h for h in hourly if h["time"] == target), None)
    f25 = _ratio(station.get("pm25"), at.get("pm2_5") if at else None)
    f10 = _ratio(station.get("pm10"), at.get("pm10") if at else None) or f25

    snap["station"] = {**station, "calibration": {"pm2_5": f25, "pm10": f10, "model_hour": target}}
    if f25 is None:
        return snap  # show the reading, but keep the model numbers untouched

    for h in hourly:
        if h.get("pm2_5") is not None:
            h["pm2_5_model"] = h["pm2_5"]
            h["pm2_5"] = round(h["pm2_5"] * f25, 1)
        if h.get("pm10") is not None and f10 is not None:
            h["pm10"] = round(h["pm10"] * f10, 1)
        pm10_level = aqi_math.category_for_aqi(aqi_math.sub_index("pm10", h.get("pm10"))).level if h.get("pm10") else 0
        h["level"] = max(aqi_math.pm25_level(h.get("pm2_5")), pm10_level)

    labels = aqi_math.POLLUTANT_LABELS
    averages = {k: snap["averages"].get(v) for k, v in labels.items()}
    if averages.get("pm2_5") is not None:
        averages["pm2_5"] = round(averages["pm2_5"] * f25, 1)
    if averages.get("pm10") is not None and f10 is not None:
        averages["pm10"] = round(averages["pm10"] * f10, 1)
    value, dominant, subs = aqi_math.naqi(averages)
    if value is not None:
        cat = aqi_math.category_for_aqi(value)
        snap["aqi"].update({
            "value": value, "category": cat.key, "label": cat.label, "level": cat.level, "color": cat.color,
            "health": cat.health, "dominant": labels.get(dominant or "", None),
            "sub_indices": {labels[k]: v for k, v in subs.items()},
            "scale": "India NAQI (estimated, calibrated to a live monitoring station)",
            "basis": "station_calibrated",
        })
    snap["averages"] = {labels[k]: v for k, v in averages.items()}
    for key in ("PM2.5", "PM10"):
        now = hourly[snap["now_index"]] if hourly else {}
        snap["pollutants_now"][key] = now.get("pm2_5" if key == "PM2.5" else "pm10", snap["pollutants_now"].get(key))
    if best_windows is not None:
        snap["windows"] = best_windows(hourly, snap["now_index"])
    return snap
