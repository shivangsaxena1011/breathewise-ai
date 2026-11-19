"""Air Quality Index maths.

Implements the Indian National Air Quality Index (NAQI, CPCB 2014) sub-index
method. Inputs are concentrations; the AQI is the maximum sub-index.
Concentrations here come from atmospheric models (CAMS via Open-Meteo), so the
result is an *estimate* of the index, never an official station reading.
"""

from __future__ import annotations

from dataclasses import dataclass

# (conc_low, conc_high, index_low, index_high) per pollutant.
# Units: µg/m³, except CO in mg/m³.  PM/NO2/SO2 use 24-h means, O3/CO 8-h means.
BREAKPOINTS: dict[str, list[tuple[float, float, int, int]]] = {
    "pm2_5": [(0, 30, 0, 50), (30, 60, 51, 100), (60, 90, 101, 200), (90, 120, 201, 300),
              (120, 250, 301, 400), (250, 500, 401, 500)],
    "pm10": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 250, 101, 200), (250, 350, 201, 300),
             (350, 430, 301, 400), (430, 600, 401, 500)],
    "nitrogen_dioxide": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 180, 101, 200), (180, 280, 201, 300),
                         (280, 400, 301, 400), (400, 800, 401, 500)],
    "sulphur_dioxide": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 380, 101, 200), (380, 800, 201, 300),
                        (800, 1600, 301, 400), (1600, 2400, 401, 500)],
    "ozone": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 168, 101, 200), (168, 208, 201, 300),
              (208, 748, 301, 400), (748, 1000, 401, 500)],
    "carbon_monoxide": [(0, 1.0, 0, 50), (1.0, 2.0, 51, 100), (2.0, 10, 101, 200), (10, 17, 201, 300),
                        (17, 34, 301, 400), (34, 50, 401, 500)],
}

POLLUTANT_LABELS = {
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "nitrogen_dioxide": "NO₂",
    "sulphur_dioxide": "SO₂",
    "ozone": "O₃",
    "carbon_monoxide": "CO",
}


@dataclass(frozen=True)
class Category:
    level: int  # 0 (best) .. 5 (worst)
    key: str
    label: str
    color: str
    health: str


CATEGORIES: list[Category] = [
    Category(0, "good", "Good", "#2e9d5b", "Minimal impact."),
    Category(1, "satisfactory", "Satisfactory", "#8cbf3f",
             "Minor breathing discomfort for sensitive people."),
    Category(2, "moderate", "Moderate", "#e0b000",
             "Breathing discomfort for people with lung or heart disease, children and older adults."),
    Category(3, "poor", "Poor", "#e8772e",
             "Breathing discomfort for most people on prolonged exposure."),
    Category(4, "very_poor", "Very Poor", "#d63a3a",
             "Respiratory illness on prolonged exposure."),
    Category(5, "severe", "Severe", "#7e2a8c",
             "Affects healthy people and seriously impacts those with existing disease."),
]


def category_for_aqi(aqi: float | None) -> Category:
    if aqi is None:
        return CATEGORIES[0]
    bounds = [50, 100, 200, 300, 400]
    for level, upper in enumerate(bounds):
        if aqi <= upper:
            return CATEGORIES[level]
    return CATEGORIES[5]


def sub_index(pollutant: str, concentration: float | None) -> int | None:
    """Linear interpolation inside the CPCB breakpoint band."""
    if concentration is None or concentration < 0 or pollutant not in BREAKPOINTS:
        return None
    bands = BREAKPOINTS[pollutant]
    for c_lo, c_hi, i_lo, i_hi in bands:
        if concentration <= c_hi:
            value = i_lo + (i_hi - i_lo) * (concentration - c_lo) / (c_hi - c_lo)
            return round(max(value, i_lo))
    return 500


def naqi(averages: dict[str, float | None]) -> tuple[int | None, str | None, dict[str, int]]:
    """Return (aqi, dominant pollutant, all sub-indices).

    CPCB requires at least three pollutants, one of which must be PM2.5 or PM10.
    """
    subs = {p: s for p in BREAKPOINTS if (s := sub_index(p, averages.get(p))) is not None}
    if len(subs) < 3 or not ({"pm2_5", "pm10"} & subs.keys()):
        return None, None, subs
    dominant = max(subs, key=lambda p: subs[p])
    return subs[dominant], dominant, subs


def pm25_level(pm25: float | None) -> int:
    """Category level from a single (hourly) PM2.5 value. Used for hour-by-hour planning."""
    if pm25 is None:
        return 0
    return category_for_aqi(sub_index("pm2_5", pm25)).level
