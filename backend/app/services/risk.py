"""Family Shield risk engine.

Deterministic and explainable: each member's risk = today's air level, raised
for sensitivity (age, conditions) and for exposure (time outdoors). Each action
carries a `why` so the UI can show the reasoning behind every recommendation.
"""

from __future__ import annotations

from typing import Any

from ..schemas import Household, Member

RISK_LABELS = ["Low", "Low", "Moderate", "High", "Very high", "Extreme"]
AGE_LABEL = {"infant": "infant", "child": "child", "teen": "teenager", "adult": "adult", "elderly": "older adult"}
RESPIRATORY = {"asthma", "copd", "heart"}


def _fmt_hour(iso: str | None) -> str:
    if not iso:
        return "the cleanest hours"
    h = int(iso[11:13])
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12} {suffix}"


def member_risk(member: Member, air_level: int) -> dict[str, Any]:
    factors: list[str] = []
    bonus = 0
    sensitive_age = member.age_group in ("infant", "child", "elderly")
    if sensitive_age:
        bonus += 1
        factors.append(f"{AGE_LABEL[member.age_group].capitalize()}s breathe more air per kg of body weight "
                       "or have weaker defences, so the same air affects them more.")
    resp = RESPIRATORY & set(member.conditions)
    if resp:
        if air_level >= 2:
            bonus += 1
        factors.append("Lung or heart conditions (" + ", ".join(sorted(resp)) + ") react to fine particles.")
    if "pregnant" in member.conditions:
        bonus += 1 if not sensitive_age else 0
        factors.append("Pregnancy: fine-particle exposure is linked to lower birth weight.")
    if member.outdoor_hours >= 4 and air_level >= 2:
        bonus += 1
        factors.append(f"About {member.outdoor_hours:g} h outdoors a day means a much larger total dose.")
    score = min(5, air_level + bonus)
    return {"score": score, "label": RISK_LABELS[score], "factors": factors}


def member_actions(member: Member, air_level: int, risk: int, best: str | None, worst: str | None) -> list[dict[str, str]]:
    acts: list[dict[str, str]] = []
    best_h, worst_h = _fmt_hour(best), _fmt_hour(worst)

    def add(text: str, why: str, priority: str = "medium") -> None:
        acts.append({"text": text, "why": why, "priority": priority})

    if member.exercises_outdoors or member.age_group in ("child", "teen"):
        if risk >= 4:
            add("Move exercise and play indoors today.",
                "Heavy breathing during exercise can pull 5–10× more polluted air deep into the lungs.", "high")
        elif risk >= 2:
            add(f"Keep outdoor exercise light and do it around {best_h}; avoid {worst_h}.",
                "The forecast shows the lowest PM2.5 in that window, so the same workout means a smaller dose.")
        else:
            add("Outdoor activity is fine today.", "Air quality is in the good-to-satisfactory range.", "low")

    if air_level >= 3 and member.age_group not in ("infant",):
        add("Wear a well-fitted N95/FFP2 mask outdoors (cloth and surgical masks do little against PM2.5).",
            "N95 respirators filter most fine particles when they seal around the nose and chin.",
            "high" if risk >= 4 else "medium")
    if member.age_group == "infant" and air_level >= 2:
        add("Keep the baby indoors in the cleanest room; do not use masks on infants.",
            "Masks are unsafe for infants; cutting exposure time is the safe protection.", "high")

    if RESPIRATORY & set(member.conditions):
        add("Keep reliever medicine handy and follow your doctor's action plan; seek care if symptoms escalate.",
            "Smog days commonly trigger asthma/COPD flare-ups and cardiac stress.", "high")

    if member.outdoor_hours >= 4 and air_level >= 2:
        add("Take breaks indoors or in a cleaner room, and stay away from roadside traffic where possible.",
            "Long outdoor shifts dominate daily exposure; even short clean-air breaks lower the total dose.", "high")

    if member.age_group == "elderly" and air_level >= 2:
        add(f"Shift the morning walk to around {best_h}, or walk indoors (corridor, mall, home).",
            "Early mornings in winter often have trapped smog near the ground.")

    if member.commute_mode in ("two_wheeler", "e_two_wheeler", "cycle", "walk") and air_level >= 3:
        add("On a two-wheeler, cycle or foot: prefer side streets over main roads and wear the mask.",
            "Concentrations next to heavy traffic can be far higher than the city average.")

    if "pregnant" in member.conditions and air_level >= 2:
        add("Limit time outdoors during smog peaks and spend most time in the cleanest room.",
            "Reducing fine-particle exposure in pregnancy is a precaution recommended by health agencies.")
    return acts


def household_actions(household: Household, air_level: int, best: str | None, worst: str | None) -> list[dict[str, str]]:
    home = household.home
    acts: list[dict[str, str]] = []
    best_h, worst_h = _fmt_hour(best), _fmt_hour(worst)
    if air_level >= 3:
        acts.append({"text": f"Keep windows closed, especially around {worst_h}. Air out briefly near {best_h}.",
                     "why": "Outdoor air is the main source of indoor PM2.5 on smog days.", "priority": "high"})
    else:
        acts.append({"text": f"Ventilate the home around {best_h} for 15–20 minutes.",
                     "why": "Fresh air removes cooking fumes and CO₂ while outdoor air is relatively clean.",
                     "priority": "medium"})
    if home.has_purifier:
        acts.append({"text": "Run the purifier on high in the bedroom where the most sensitive person sleeps; keep the door closed.",
                     "why": "A purifier cleans one closed room well rather than a whole house poorly.", "priority": "high"})
    elif air_level >= 3:
        acts.append({"text": "No purifier? A box fan with a MERV-13 filter taped to it makes a low-cost DIY air cleaner.",
                     "why": "DIY fan-filter units have been shown to remove a large share of fine particles in a room.",
                     "priority": "medium"})
    if home.cooking_fuel in ("biomass", "kerosene"):
        acts.append({"text": "Cook with ventilation or outdoors-side doors open, and switch to LPG/induction if possible.",
                     "why": "Solid-fuel and kerosene cooking is one of the largest indoor pollution sources.", "priority": "high"})
    if home.smoker_at_home:
        acts.append({"text": "Keep the home smoke-free; smoke only outside, away from windows.",
                     "why": "Indoor smoking can raise PM2.5 more than a severe smog day outside.", "priority": "high"})
    if home.burns_incense and air_level >= 2:
        acts.append({"text": "Skip incense, mosquito coils and candles on smog days.",
                     "why": "They release fine particles indoors exactly when you are sealing the home.", "priority": "medium"})
    acts.append({"text": "Wet-mop floors and dust with a damp cloth instead of sweeping.",
                 "why": "Dry sweeping lifts settled dust back into the air you breathe.", "priority": "low"})
    acts.append({"text": "Avoid idling vehicles and burning leaves or waste.",
                 "why": "These are direct local sources of the smog your family is breathing.", "priority": "low"})
    return acts


def build_plan(household: Household, snapshot: dict[str, Any]) -> dict[str, Any]:
    level_now = snapshot["aqi"]["level"] or 0
    windows = snapshot.get("windows") or []
    today = windows[0] if windows else None
    best = today["best"]["start"] if today else None
    worst = today["worst"]["start"] if today else None
    air_level = max(level_now, today["worst"]["level"] if today else 0)

    members = []
    for m in household.members:
        r = member_risk(m, air_level)
        members.append({
            "name": m.name,
            "age_group": m.age_group,
            "risk": r,
            "actions": member_actions(m, air_level, r["score"], best, worst),
        })
    # Ties (e.g. everyone capped at 5) go to the member with more sensitivity factors.
    top = max(members, key=lambda x: (x["risk"]["score"], len(x["risk"]["factors"])))
    return {
        "air_level": air_level,
        "aqi": snapshot["aqi"],
        "best_window": best,
        "worst_window": worst,
        "household_risk": top["risk"]["label"],
        "most_at_risk": top["name"],
        "members": members,
        "household_actions": household_actions(household, air_level, best, worst),
        "explanation": {
            "data_used": [
                f"Estimated AQI {snapshot['aqi']['value']} ({snapshot['aqi']['label']}) at {snapshot['observed_at']}",
                f"Today's cleanest 2-h window starts {_fmt_hour(best)}; dirtiest {_fmt_hour(worst)}" if today else
                "No hourly forecast available",
                "Household profile you entered (ages, conditions, time outdoors)",
            ],
            "method": "Risk = today's worst air level (0–5), +1 for a sensitive age, +1 for lung/heart conditions "
                      "or pregnancy, +1 for 4+ hours outdoors; capped at 5.",
            "reliability": "Air data is a regional model estimate; actions follow general public-health guidance. "
                           "Not a medical diagnosis.",
        },
        "source": snapshot["source"],
    }
