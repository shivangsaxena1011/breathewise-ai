"""Personal exposure (inhaled dose) estimates.

Inhaled dose (µg) = PM2.5 concentration (µg/m³) × breathing rate (m³/h) × hours.
Breathing rates are typical adult values used in exposure science.
"""

from __future__ import annotations

import math
from typing import Any

BREATHING_M3_PER_H = {"rest": 0.5, "light": 1.0, "moderate": 1.6, "vigorous": 3.0}


def inhaled_dose(pm25: float, hours: float, intensity: str = "moderate") -> float:
    return pm25 * BREATHING_M3_PER_H[intensity] * hours


def _avg_pm25(hourly: list[dict[str, Any]], start_index: int, duration_min: int) -> float | None:
    n = max(1, math.ceil(duration_min / 60))
    vals = [h["pm2_5"] for h in hourly[start_index:start_index + n] if h.get("pm2_5") is not None]
    return sum(vals) / len(vals) if vals else None


def exercise_shift(snapshot: dict[str, Any], current_hour: int, duration_min: int, intensity: str) -> dict[str, Any]:
    """Compare exercising at the usual hour vs the cleanest daytime hour in the next 24 h."""
    hourly = snapshot["hourly"]
    now = snapshot["now_index"]
    upcoming = list(range(now, min(len(hourly), now + 24)))
    if not upcoming:
        return {"available": False}

    usual_idx = next((i for i in upcoming if int(hourly[i]["time"][11:13]) == current_hour), None)
    candidates = [i for i in upcoming if 6 <= int(hourly[i]["time"][11:13]) <= 20 and hourly[i].get("pm2_5") is not None]
    if usual_idx is None or not candidates:
        return {"available": False}
    def avg_or_inf(i: int) -> float:
        v = _avg_pm25(hourly, i, duration_min)
        return float("inf") if v is None else v

    # The usual hour is always a candidate, so the suggestion is never worse than doing nothing.
    best_idx = min([usual_idx, *candidates], key=avg_or_inf)
    usual_pm = _avg_pm25(hourly, usual_idx, duration_min)
    best_pm = _avg_pm25(hourly, best_idx, duration_min)
    if usual_pm is None or best_pm is None:
        return {"available": False}
    hours = duration_min / 60
    d_usual = inhaled_dose(usual_pm, hours, intensity)
    d_best = inhaled_dose(best_pm, hours, intensity)
    pct = 0 if d_usual == 0 else (d_usual - d_best) / d_usual * 100
    return {
        "available": True,
        "usual": {"time": hourly[usual_idx]["time"], "pm2_5": round(usual_pm, 1), "dose_ug": round(d_usual, 1)},
        "best": {"time": hourly[best_idx]["time"], "pm2_5": round(best_pm, 1), "dose_ug": round(d_best, 1)},
        "dose_reduction_pct": round(pct),
        "assumptions": [
            f"Breathing rate {BREATHING_M3_PER_H[intensity]} m³/h for {intensity} exercise (typical adult)",
            f"{duration_min} min session; PM2.5 from the hourly model forecast",
            "Dose = concentration × breathing rate × time; real exposure varies by route and traffic",
        ],
    }
