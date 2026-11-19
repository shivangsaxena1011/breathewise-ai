"""Fetch and interpret air-quality + weather data from Open-Meteo (free, no key).

Open-Meteo's air-quality API serves CAMS atmospheric-model output. Every
response we build is labelled as a model estimate, with source and timestamp,
so the UI never presents it as a ground-station measurement.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any

import httpx

from ..config import settings
from . import aqi as aqi_math
from . import stations
from .cache import TTLCache

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

POLLUTANTS = ["pm2_5", "pm10", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "carbon_monoxide"]
SOURCE = {
    "name": "Copernicus Atmosphere Monitoring Service (CAMS) via Open-Meteo",
    "url": "https://open-meteo.com/en/docs/air-quality-api",
    "kind": "model_estimate",
    "note": "Modelled concentrations on a ~10–45 km grid, not a ground-station reading. "
            "Local hotspots (busy roads, burning) can be much worse.",
}

_cache = TTLCache(ttl_seconds=settings.air_cache_seconds)


class UpstreamError(RuntimeError):
    """Raised when Open-Meteo cannot be reached or returns unusable data."""


def _key(*parts: Any) -> str:
    return "|".join(str(p) for p in parts)


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> Any:
    try:
        resp = await client.get(url, params=params, timeout=12.0)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpstreamError(f"Data provider unavailable ({type(exc).__name__})") from exc


async def geocode(client: httpx.AsyncClient, query: str, language: str = "en") -> list[dict[str, Any]]:
    key = _key("geo", query.lower(), language)
    if (hit := _cache.get(key)) is not None:
        return hit
    data = await _get_json(client, GEOCODE_URL, {"name": query, "count": 6, "language": language, "format": "json"})
    results = [
        {
            "name": r.get("name"),
            "admin1": r.get("admin1"),
            "country": r.get("country"),
            "country_code": r.get("country_code"),
            "lat": r.get("latitude"),
            "lon": r.get("longitude"),
        }
        for r in (data or {}).get("results", []) or []
        if r.get("latitude") is not None and r.get("longitude") is not None
    ]
    _cache.set(key, results)
    return results


def _window_mean(series: list[float | None], end: int, hours: int) -> float | None:
    start = max(0, end - hours + 1)
    values = [v for v in series[start:end + 1] if v is not None]
    # Require at least 2/3 coverage, as CPCB does for 24-h averages.
    if len(values) < max(1, int(hours * 2 / 3)):
        return None
    return round(mean(values), 1)


def _current_index(times: list[str], current_time: str | None, utc_offset_seconds: int | None = None) -> int:
    if current_time and current_time in times:
        return times.index(current_time)
    if current_time:
        prefix = current_time[:13]  # match on the hour
        for i, t in enumerate(times):
            if t.startswith(prefix):
                return i
    # No usable "current" block: use the last hour at or before the location's local time now.
    local_now = (datetime.now(UTC) + timedelta(seconds=utc_offset_seconds or 0)).strftime("%Y-%m-%dT%H:00")
    past = [i for i, t in enumerate(times) if t <= local_now]
    return past[-1] if past else 0


def _smog_drivers(weather_now: dict[str, Any]) -> list[dict[str, str]]:
    """Plain-language reasons pollution may build up, from weather signals."""
    drivers: list[dict[str, str]] = []
    wind = weather_now.get("wind_speed_10m")
    blh = weather_now.get("boundary_layer_height")
    rh = weather_now.get("relative_humidity_2m")
    temp = weather_now.get("temperature_2m")
    if wind is not None and wind < 6:
        drivers.append({"key": "low_wind", "text": f"Low wind ({wind:.0f} km/h) — pollution is not being blown away."})
    if blh is not None and blh < 400:
        drivers.append({"key": "low_mixing",
                        "text": f"Shallow mixing layer (~{blh:.0f} m) — smoke and dust are trapped near the ground."})
    if rh is not None and rh > 80 and temp is not None and temp < 18:
        drivers.append({"key": "fog", "text": "Cold, humid air — fog can mix with smoke to form dense smog."})
    return drivers


def _window(hours: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    """Cleanest and dirtiest consecutive 2-hour daytime (6:00–21:00) windows within `hours`."""
    # A window starts between 06:00 and 20:00 and covers that hour plus the next one (so it ends by 21:00).
    day = [h for h in hours if h["pm2_5"] is not None and 6 <= int(h["time"][11:13]) <= 21]
    pairs = [(a, b) for a, b in zip(day, day[1:], strict=False) if b["time"][:10] == a["time"][:10]
             and int(b["time"][11:13]) == int(a["time"][11:13]) + 1]
    if not pairs:
        return None
    avg = lambda p: (p[0]["pm2_5"] + p[1]["pm2_5"]) / 2  # noqa: E731
    best, worst = min(pairs, key=avg), max(pairs, key=avg)
    return {
        "date": label,
        "best": {"start": best[0]["time"], "pm2_5": round(avg(best), 1), "level": aqi_math.pm25_level(avg(best))},
        "worst": {"start": worst[0]["time"], "pm2_5": round(avg(worst), 1), "level": aqi_math.pm25_level(avg(worst))},
    }


def _best_windows(hourly: list[dict[str, Any]], now_index: int) -> list[dict[str, Any]]:
    """First entry: the rolling next 24 h (so late-evening users still get a useful plan); then each later day."""
    out = []
    if (nxt := _window(hourly[now_index:now_index + 24], "next_24h")) is not None:
        out.append(nxt)
    days = sorted({h["time"][:10] for h in hourly[now_index:]})[1:]
    for d in days:
        if (w := _window([h for h in hourly if h["time"].startswith(d)], d)) is not None:
            out.append(w)
    return out


def build_snapshot(air: dict[str, Any], weather: dict[str, Any] | None) -> dict[str, Any]:
    """Pure function: turn raw Open-Meteo payloads into the app's snapshot model."""
    hourly_raw = air.get("hourly") or {}
    times: list[str] = hourly_raw.get("time") or []
    if not times:
        raise UpstreamError("No hourly air-quality data for this location")
    current = air.get("current") or {}
    idx = _current_index(times, current.get("time"), air.get("utc_offset_seconds"))

    series = {p: hourly_raw.get(p) or [None] * len(times) for p in POLLUTANTS}
    us_series = hourly_raw.get("us_aqi") or [None] * len(times)
    # CO arrives in µg/m³; CPCB breakpoints use mg/m³.
    co_mg = [None if v is None else v / 1000 for v in series["carbon_monoxide"]]

    averages = {
        "pm2_5": _window_mean(series["pm2_5"], idx, 24),
        "pm10": _window_mean(series["pm10"], idx, 24),
        "nitrogen_dioxide": _window_mean(series["nitrogen_dioxide"], idx, 24),
        "sulphur_dioxide": _window_mean(series["sulphur_dioxide"], idx, 24),
        "ozone": _window_mean(series["ozone"], idx, 8),
        "carbon_monoxide": _window_mean(co_mg, idx, 8),
    }
    index, dominant, subs = aqi_math.naqi(averages)
    cat = aqi_math.category_for_aqi(index)

    w_hourly = (weather or {}).get("hourly") or {}
    w_times: list[str] = w_hourly.get("time") or []
    w_lookup = {t: i for i, t in enumerate(w_times)}

    def w_at(t: str, var: str) -> float | None:
        i = w_lookup.get(t)
        vals = w_hourly.get(var) or []
        return vals[i] if i is not None and i < len(vals) else None

    hourly = []
    for i, t in enumerate(times):
        pm25, pm10 = series["pm2_5"][i], series["pm10"][i]
        level = max(aqi_math.pm25_level(pm25),
                    aqi_math.category_for_aqi(aqi_math.sub_index("pm10", pm10)).level if pm10 is not None else 0)
        hourly.append({
            "time": t,
            "pm2_5": pm25,
            "pm10": pm10,
            "us_aqi": us_series[i] if i < len(us_series) else None,
            "level": level,
            "wind_speed_10m": w_at(t, "wind_speed_10m"),
            "temperature_2m": w_at(t, "temperature_2m"),
        })

    now_time = times[idx]
    weather_now = {var: w_at(now_time, var) for var in
                   ("temperature_2m", "relative_humidity_2m", "wind_speed_10m", "boundary_layer_height")}

    return {
        "location": {"lat": air.get("latitude"), "lon": air.get("longitude"), "timezone": air.get("timezone"),
                     "utc_offset_seconds": air.get("utc_offset_seconds") or 0},
        "observed_at": now_time,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "aqi": {
            "value": index,
            "scale": "India NAQI (CPCB method, estimated)",
            "category": cat.key if index is not None else None,
            "label": cat.label if index is not None else "Unavailable",
            "level": cat.level if index is not None else None,
            "color": cat.color if index is not None else "#888888",
            "health": cat.health if index is not None else "Not enough data to compute an index.",
            "dominant": aqi_math.POLLUTANT_LABELS.get(dominant or "", None),
            "sub_indices": {aqi_math.POLLUTANT_LABELS[k]: v for k, v in subs.items()},
            "us_aqi": current.get("us_aqi"),
            "basis": "model",
        },
        "pollutants_now": {
            aqi_math.POLLUTANT_LABELS[p]: (
                current.get(p) / 1000 if p == "carbon_monoxide" and current.get(p) is not None else current.get(p)
            )
            for p in POLLUTANTS
        },
        "averages": {aqi_math.POLLUTANT_LABELS[k]: v for k, v in averages.items()},
        "units": {"default": "µg/m³", "CO": "mg/m³"},
        "weather_now": weather_now,
        "smog_drivers": _smog_drivers(weather_now),
        "hourly": hourly,
        "now_index": idx,
        "windows": _best_windows(hourly, idx),
        "source": SOURCE,
    }


async def get_snapshot(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    lat, lon = round(lat, 2), round(lon, 2)
    key = _key("snap", lat, lon)
    if (hit := _cache.get(key)) is not None:
        return hit
    air = await _get_json(client, AIR_URL, {
        "latitude": lat, "longitude": lon,
        "current": ",".join(["us_aqi", *POLLUTANTS]),
        "hourly": ",".join([*POLLUTANTS, "us_aqi"]),
        "past_days": 1, "forecast_days": 3, "timezone": "auto",
    })
    try:
        weather = await _get_json(client, WEATHER_URL, {
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,boundary_layer_height",
            "past_days": 1, "forecast_days": 3, "timezone": "auto",
        })
    except UpstreamError:
        weather = None  # air data alone is still useful
    snapshot = build_snapshot(air, weather)
    station = await stations.nearest_station(client, lat, lon)
    snapshot = stations.apply_station(snapshot, station, _best_windows)
    snapshot.setdefault("station", None)
    _cache.set(key, snapshot)
    return snapshot


async def get_area_grid(client: httpx.AsyncClient, lat: float, lon: float, step: float = 0.4) -> dict[str, Any]:
    """Current PM2.5 on a 5x5 model grid around a point (regional view, not hyperlocal stations)."""
    lat, lon = round(lat, 2), round(lon, 2)
    key = _key("grid", lat, lon, step)
    if (hit := _cache.get(key)) is not None:
        return hit
    offsets = [-2, -1, 0, 1, 2]
    def wrap(x: float) -> float:
        return ((x + 180) % 360) - 180

    pts = [(round(max(-89.9, min(89.9, lat + dy * step)), 3), round(wrap(lon + dx * step), 3))
           for dy in offsets for dx in offsets]
    data = await _get_json(client, AIR_URL, {
        "latitude": ",".join(str(p[0]) for p in pts),
        "longitude": ",".join(str(p[1]) for p in pts),
        "current": "pm2_5,pm10,us_aqi",
        "timezone": "auto",
    })
    items = data if isinstance(data, list) else [data]
    cells = []
    for (plat, plon), item in zip(pts, items, strict=False):
        cur = (item or {}).get("current") or {}
        pm25 = cur.get("pm2_5")
        level = aqi_math.pm25_level(pm25)
        cells.append({"lat": plat, "lon": plon, "pm2_5": pm25, "pm10": cur.get("pm10"),
                      "level": level, "color": aqi_math.CATEGORIES[level].color})
    result = {"center": {"lat": lat, "lon": lon}, "step_deg": step, "cells": cells, "source": SOURCE}
    _cache.set(key, result)
    return result


def clear_cache() -> None:
    _cache.clear()
