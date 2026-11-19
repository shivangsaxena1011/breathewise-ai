"""Indoor Air Doctor: ventilation verdict, room-by-room tips, purifier sizing."""

from __future__ import annotations

from typing import Any

from ..schemas import Home, Room

TARGET_ACH = 5  # clean-air changes per hour commonly recommended for a room purifier
M3H_TO_CFM = 0.5886

ROOM_TIPS: dict[str, list[dict[str, str]]] = {
    "kitchen": [
        {"text": "Run the exhaust fan/chimney while cooking and for 10 minutes after.",
         "why": "Frying and high-heat cooking create PM2.5 spikes that can exceed outdoor smog levels."},
        {"text": "Use lids, and prefer boiling/steaming to deep frying on smog days.",
         "why": "Less smoke and oil aerosol is produced in the first place."},
    ],
    "bedroom": [
        {"text": "Make this the cleanest room: door closed, purifier or DIY filter running at night.",
         "why": "You spend ~8 hours here, so it gives the biggest exposure reduction."},
        {"text": "Wash bedding weekly in hot water.", "why": "Removes settled dust and allergens."},
    ],
    "living": [
        {"text": "Wet-mop floors; vacuum only with a HEPA vacuum.", "why": "Dry sweeping re-suspends fine dust."},
        {"text": "No incense, coils or candles while windows are closed.", "why": "They are hidden indoor PM2.5 sources."},
    ],
    "kids": [
        {"text": "Put the purifier where children nap/play; keep toys and floor dust-free.",
         "why": "Children breathe faster and spend more time near the floor."},
    ],
    "study": [
        {"text": "Crack the window or run the fan during clean hours to keep CO₂ down.",
         "why": "A sealed small room builds up CO₂, which causes drowsiness and headaches."},
    ],
    "bathroom": [
        {"text": "Use the exhaust fan after showers.", "why": "Prevents damp and mould, another indoor irritant."},
    ],
}

FUEL_TIPS = {
    "biomass": {"text": "Biomass (wood/dung) cooking: improve ventilation and move towards LPG/induction when possible.",
                "why": "Solid-fuel smoke is one of the largest health risks from indoor air in India."},
    "kerosene": {"text": "Replace kerosene stoves/lamps where possible; ventilate when using them.",
                 "why": "Kerosene releases fine particles and gases indoors."},
}


def ventilation_verdict(snapshot: dict[str, Any]) -> dict[str, Any]:
    level = snapshot["aqi"]["level"] or 0
    now = snapshot["hourly"][snapshot["now_index"]] if snapshot["hourly"] else {}
    now_level = now.get("level", level)
    windows = snapshot.get("windows") or []
    best = windows[0]["best"] if windows else None
    if now_level <= 1 and level >= 3:
        verdict, text = "brief", "Cleaner than the day's average right now — air out for 5–10 minutes, then close up."
    elif now_level <= 1:
        verdict, text = "open", "Outdoor air is relatively clean now — open windows for 15–20 minutes."
    elif now_level == 2:
        verdict, text = "brief", "Moderate outside — short cross-ventilation (5–10 min) is fine; avoid long airing."
    else:
        verdict, text = "closed", "Keep windows closed now: outdoor air is dirtier than well-sealed indoor air."
    return {
        "verdict": verdict,
        "text": text,
        "now_pm2_5": now.get("pm2_5"),
        "best_window": best,
        "why": "Opening windows exchanges indoor air with outdoor air; that helps only when outdoor PM2.5 is lower "
               "than what builds up indoors (cooking, dust).",
    }


def purifier_size(room: Room) -> dict[str, Any]:
    volume = room.area_m2 * room.height_m
    cadr_m3h = volume * TARGET_ACH
    return {
        "volume_m3": round(volume, 1),
        "cadr_m3h": round(cadr_m3h),
        "cadr_cfm": round(cadr_m3h * M3H_TO_CFM),
        "basis": f"{room.area_m2:g} m² × {room.height_m:g} m × {TARGET_ACH} air changes/hour",
    }


def diagnose(home: Home, rooms: list[Room], snapshot: dict[str, Any]) -> dict[str, Any]:
    level = snapshot["aqi"]["level"] or 0
    out_rooms = []
    for room in rooms:
        tips = list(ROOM_TIPS.get(room.kind, []))
        if room.kind == "kitchen" and home.cooking_fuel in FUEL_TIPS:
            tips.insert(0, FUEL_TIPS[home.cooking_fuel])
        out_rooms.append({"kind": room.kind, "tips": tips, "purifier": purifier_size(room)})

    general = []
    if home.smoker_at_home:
        general.append({"text": "Make the home smoke-free.", "why": "Indoor tobacco smoke is a major PM2.5 source."})
    if home.has_pets:
        general.append({"text": "Groom pets outdoors-side and vacuum with HEPA.", "why": "Reduces dander and allergens."})
    if home.has_purifier:
        general.append({"text": "Check the filter: replace HEPA every 6–12 months (sooner in heavy smog).",
                        "why": "A clogged filter sharply reduces clean-air delivery."})
    else:
        general.append({"text": "Low-cost option: tape a MERV-13 filter to a box fan (DIY air cleaner).",
                        "why": "A well-built fan-filter unit can deliver clean air comparable to budget purifiers."})
    if level >= 3:
        general.append({"text": "Seal obvious gaps around windows/doors with tape or draught strips.",
                        "why": "Less infiltration of smog when windows are closed."})
    general.append({"text": "Want to know your actual indoor level? A low-cost PM2.5 sensor helps verify these steps.",
                    "why": "Indoor levels vary hugely between homes; measuring beats guessing."})
    return {"ventilation": ventilation_verdict(snapshot), "rooms": out_rooms, "general": general,
            "aqi": snapshot["aqi"], "source": snapshot["source"]}
