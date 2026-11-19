"""Proactive Guardian alerts and the adaptive daily routine."""

from __future__ import annotations

from typing import Any

from ..schemas import Activity, Household
from . import aqi as aqi_math
from .risk import _fmt_hour


def _hour_index(hourly: list[dict[str, Any]]) -> dict[str, int]:
    return {h["time"][:13]: i for i, h in enumerate(hourly)}


def alerts(activities: list[Activity], snapshot: dict[str, Any], household: Household | None) -> dict[str, Any]:
    hourly = snapshot["hourly"]
    lookup = _hour_index(hourly)
    sensitive_household = bool(household and any(
        m.age_group in ("infant", "child", "elderly") or m.conditions for m in household.members))
    out = []
    for act in activities:
        i = lookup.get(act.start[:13])
        if i is None:
            out.append({"activity": act.title, "start": act.start, "status": "unknown",
                        "message": "Outside the 3-day forecast range."})
            continue
        n = max(1, round(act.duration_min / 60))
        vals = [h["pm2_5"] for h in hourly[i:i + n] if h.get("pm2_5") is not None]
        pm = sum(vals) / len(vals) if vals else None
        level = aqi_math.pm25_level(pm)
        threshold = 2 if (act.sensitive or sensitive_household) else 3
        day = act.start[:10]
        same_day = [j for j, h in enumerate(hourly) if h["time"].startswith(day)
                    and 6 <= int(h["time"][11:13]) <= 20 and h.get("pm2_5") is not None]
        best_j = min(same_day, key=lambda j: hourly[j]["pm2_5"]) if same_day else None
        item = {"activity": act.title, "start": act.start, "who": act.who,
                "pm2_5": None if pm is None else round(pm, 1), "level": level,
                "category": aqi_math.CATEGORIES[level].label}
        if level >= threshold:
            alt = hourly[best_j] if best_j is not None else None
            better = alt is not None and alt["pm2_5"] < (pm or 0) * 0.8
            item["status"] = "warn"
            item["message"] = (
                f"Forecast {aqi_math.CATEGORIES[level].label} air during '{act.title}'. "
                + (f"Consider moving it to {_fmt_hour(alt['time'])} (PM2.5 ≈ {alt['pm2_5']:.0f} vs {pm:.0f} µg/m³) "
                   "or doing it indoors." if better else "Consider doing it indoors or shortening it.")
            )
            if better:
                item["suggested_time"] = alt["time"]
        else:
            item["status"] = "ok"
            item["message"] = f"Air looks {aqi_math.CATEGORIES[level].label.lower()} for '{act.title}'."
        out.append(item)
    return {"alerts": out, "source": snapshot["source"], "observed_at": snapshot["observed_at"]}


def routine(household: Household, snapshot: dict[str, Any], commute_mode: str | None) -> dict[str, Any]:
    windows = snapshot.get("windows") or []
    today = windows[0] if windows else None
    best = today["best"]["start"] if today else None
    worst = today["worst"]["start"] if today else None
    level = max(snapshot["aqi"]["level"] or 0, today["worst"]["level"] if today else 0)
    has_kids = any(m.age_group in ("infant", "child") for m in household.members)
    has_elderly = any(m.age_group == "elderly" for m in household.members)
    exercisers = [m.name for m in household.members if m.exercises_outdoors]

    steps: list[dict[str, str]] = [
        {"time": "06:30", "title": "Check today's air", "detail": "Open BreatheWise and check the cleanest window before planning outdoor time."},
    ]
    if exercisers:
        when = _fmt_hour(best)
        detail = (f"Move exercise indoors (yoga, stretching, stairs)." if level >= 4 else
                  f"Best outdoor slot today is around {when}." if level >= 2 else "Air is fine — enjoy outdoor exercise.")
        steps.append({"time": best[11:16] if best and 2 <= level < 4 else "07:00",
                      "title": f"Exercise ({', '.join(exercisers)})", "detail": detail})
    if commute_mode in ("car_petrol", "car_diesel", "two_wheeler"):
        steps.append({"time": "08:30", "title": "Commute",
                      "detail": "Try bus/metro or carpool today; if driving, keep windows up with recirculation on and don't idle."})
    else:
        steps.append({"time": "08:30", "title": "Commute",
                      "detail": "Great low-emission choice. Prefer quieter streets; wear an N95 if air is Poor or worse."})
    if has_kids:
        steps.append({"time": best[11:16] if best and level < 3 else "10:00", "title": "Kids' outdoor play",
                      "detail": "Keep it indoors today." if level >= 3 else f"Schedule play around {_fmt_hour(best)}."})
    steps.append({"time": best[11:16] if best else "13:00", "title": "Air out the home",
                  "detail": "Ventilate 10–15 min during the cleanest hour." if level <= 3 else
                  "Skip airing today; keep windows shut and run the purifier."})
    if has_elderly:
        steps.append({"time": "16:00", "title": "Elders' walk",
                      "detail": "Walk indoors today." if level >= 3 else f"Short walk near {_fmt_hour(best)}."})
    steps.append({"time": worst[11:16] if worst else "19:00", "title": "Smog peak — stay in",
                  "detail": "Windows closed, purifier on, no incense or frying without exhaust."})
    steps.append({"time": "21:00", "title": "Log eco-actions",
                  "detail": "Record trips and habits in the Eco Tracker to see your weekly impact."})
    steps.sort(key=lambda s: s["time"])
    return {"steps": steps, "air_level": level, "best_window": best, "worst_window": worst,
            "aqi": snapshot["aqi"], "source": snapshot["source"]}
