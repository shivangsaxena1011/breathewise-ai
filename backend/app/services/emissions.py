"""Transport and household emission estimates, with every assumption exposed.

Factors are derived from fuel use × fuel carbon content so the maths can be
shown to the user. They are typical Indian-context values, not measurements
of the user's own vehicle; the UI lets people see (and question) each one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# kg CO2 per litre / kg of fuel (tank-to-wheel)
PETROL_KG_PER_L = 2.31
DIESEL_KG_PER_L = 2.68
CNG_KG_PER_KG = 2.75
GRID_KG_PER_KWH = 0.72  # approx. Indian grid average (CEA CO2 baseline database, recent years)

# Each mode: per-vehicle-km factor, typical passengers, and how it was derived.
MODES: dict[str, dict[str, Any]] = {
    "car_petrol": {"label": "Petrol car", "kg_per_vkm": PETROL_KG_PER_L / 15, "shared_by_trip": True,
                   "basis": "2.31 kg CO₂/L ÷ 15 km/L"},
    "car_diesel": {"label": "Diesel car", "kg_per_vkm": DIESEL_KG_PER_L / 18, "shared_by_trip": True,
                   "basis": "2.68 kg CO₂/L ÷ 18 km/L"},
    "car_cng": {"label": "CNG car", "kg_per_vkm": CNG_KG_PER_KG / 25, "shared_by_trip": True,
                "basis": "2.75 kg CO₂/kg ÷ 25 km/kg"},
    "car_ev": {"label": "Electric car", "kg_per_vkm": 0.15 * GRID_KG_PER_KWH, "shared_by_trip": True,
               "basis": "0.15 kWh/km × 0.72 kg CO₂/kWh grid"},
    "two_wheeler": {"label": "Petrol scooter/bike", "kg_per_vkm": PETROL_KG_PER_L / 45, "shared_by_trip": True,
                    "basis": "2.31 kg CO₂/L ÷ 45 km/L"},
    "e_two_wheeler": {"label": "Electric scooter", "kg_per_vkm": 0.03 * GRID_KG_PER_KWH, "shared_by_trip": True,
                      "basis": "0.03 kWh/km × 0.72 kg CO₂/kWh grid"},
    "auto_cng": {"label": "CNG auto-rickshaw", "kg_per_pkm": CNG_KG_PER_KG / 35 / 1.5, "shared_by_trip": False,
                 "basis": "2.75 kg CO₂/kg ÷ 35 km/kg ÷ 1.5 passengers"},
    "bus": {"label": "City bus", "kg_per_pkm": DIESEL_KG_PER_L / 3.5 / 30, "shared_by_trip": False,
            "basis": "2.68 kg CO₂/L ÷ 3.5 km/L ÷ 30 avg passengers"},
    "metro": {"label": "Metro / suburban rail", "kg_per_pkm": 0.03, "shared_by_trip": False,
              "basis": "≈0.03 kg CO₂ per passenger-km (typical electric metro, grid-dependent)"},
    "cycle": {"label": "Cycle", "kg_per_pkm": 0.0, "shared_by_trip": False, "basis": "No fuel"},
    "walk": {"label": "Walk", "kg_per_pkm": 0.0, "shared_by_trip": False, "basis": "No fuel"},
}

# Local smog relevance (qualitative): exhaust PM/NOx at street level.
LOCAL_POLLUTION = {
    "car_petrol": "medium", "car_diesel": "high", "car_cng": "low", "car_ev": "none at tailpipe",
    "two_wheeler": "medium", "e_two_wheeler": "none at tailpipe", "auto_cng": "low", "bus": "low per person",
    "metro": "none at street level", "cycle": "none", "walk": "none",
}

EXPOSURE_NOTE = (
    "Lower emissions ≠ lower personal exposure. Walking or cycling along a busy road can mean breathing more "
    "polluted air even though you emit nothing. Choose quieter streets and cleaner hours."
)


def per_person_km(mode: str, occupants: int = 1) -> float:
    m = MODES[mode]
    if "kg_per_vkm" in m:
        return m["kg_per_vkm"] / max(1, occupants)
    return m["kg_per_pkm"]


def compare_trip(distance_km: float, occupants: int = 1, modes: Sequence[str] | None = None) -> dict[str, Any]:
    """Per-person CO2 for one trip across travel modes, cleanest first, with each row relative to the worst."""
    chosen = list(modes) if modes else list(MODES)
    rows = []
    for key in chosen:
        m = MODES[key]
        kg = per_person_km(key, occupants) * distance_km
        rows.append({
            "mode": key,
            "label": m["label"],
            "kg_co2_per_person": round(kg, 3),
            "basis": m["basis"] + (f" ÷ {occupants} occupants" if m["shared_by_trip"] and occupants > 1 else ""),
            "local_pollution": LOCAL_POLLUTION[key],
        })
    rows.sort(key=lambda r: r["kg_co2_per_person"])
    worst = max(r["kg_co2_per_person"] for r in rows) or 1
    for r in rows:
        r["relative"] = round(r["kg_co2_per_person"] / worst, 3)
    return {"distance_km": distance_km, "occupants": occupants, "rows": rows, "exposure_note": EXPOSURE_NOTE}


def mode_shift(from_mode: str, to_mode: str, km_one_way: float, days_per_week: int, occupants: int = 1) -> dict[str, Any]:
    """Weekly/annual CO2 change. The current trip is assumed solo; `occupants` applies to the new option (carpooling)."""
    km_week = km_one_way * 2 * days_per_week
    before = per_person_km(from_mode, 1) * km_week
    after = per_person_km(to_mode, occupants) * km_week
    saved_week = before - after
    return {
        "km_per_week": round(km_week, 1),
        "kg_co2_week_before": round(before, 2),
        "kg_co2_week_after": round(after, 2),
        "kg_co2_saved_week": round(saved_week, 2),
        "kg_co2_saved_year": round(saved_week * 52, 1),
        "assumptions": [
            f"{MODES[from_mode]['label']}: {MODES[from_mode]['basis']}",
            f"{MODES[to_mode]['label']}: {MODES[to_mode]['basis']}",
            f"{km_one_way:g} km each way, {days_per_week} days/week, 52 weeks/year",
        ],
    }


def energy_saving(kwh_per_month: float) -> dict[str, Any]:
    kg_year = kwh_per_month * 12 * GRID_KG_PER_KWH
    return {
        "kg_co2_saved_year": round(kg_year, 1),
        "assumptions": [f"{kwh_per_month:g} kWh/month saved × 12 × {GRID_KG_PER_KWH} kg CO₂/kWh (Indian grid average)",
                        "Coal power plants are also a major regional source of PM2.5 and SO₂."],
    }


# Open burning of mixed waste: PM2.5 emission factor, literature range roughly 5–15 g/kg.
WASTE_PM25_G_PER_KG = 8.0


def waste_burning(kg_per_week: float) -> dict[str, Any]:
    g_year = kg_per_week * 52 * WASTE_PM25_G_PER_KG
    return {
        "pm25_g_avoided_year": round(g_year),
        "assumptions": [f"{kg_per_week:g} kg/week of mixed waste/leaves not burned",
                        f"≈{WASTE_PM25_G_PER_KG:g} g PM2.5 per kg burned (published range ~5–15 g/kg)",
                        "Smoke is released at ground level right where people live, so local exposure drops sharply."],
    }
