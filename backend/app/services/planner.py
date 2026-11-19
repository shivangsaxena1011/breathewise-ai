"""Proactive Guardian alerts and the adaptive daily routine (English / Hindi)."""

from __future__ import annotations

import math
from typing import Any

from ..schemas import Activity, Household
from . import aqi as aqi_math
from .i18n import category, fmt_hour, tr


def _hour_index(hourly: list[dict[str, Any]]) -> dict[str, int]:
    return {h["time"][:13]: i for i, h in enumerate(hourly)}


def alerts(activities: list[Activity], snapshot: dict[str, Any], household: Household | None,
           lang: str = "en") -> dict[str, Any]:
    hourly = snapshot["hourly"]
    lookup = _hour_index(hourly)
    now = snapshot.get("now_index", 0)
    sensitive_household = bool(household and any(
        m.age_group in ("infant", "child", "elderly") or m.conditions for m in household.members))
    out = []
    for act in activities:
        i = lookup.get(act.start[:13])
        if i is None:
            out.append({"activity": act.title, "start": act.start, "status": "unknown",
                        "message": tr(lang, "Outside the 3-day forecast range.", "यह समय 3 दिन के पूर्वानुमान से बाहर है।")})
            continue
        if i < now:
            out.append({"activity": act.title, "start": act.start, "status": "unknown",
                        "message": tr(lang, "That time has already passed — pick a time later today or in the next 2 days.",
                                      "यह समय बीत चुका है — आज बाद का या अगले 2 दिनों का कोई समय चुनें।")})
            continue
        n = max(1, math.ceil(act.duration_min / 60))
        vals = [h["pm2_5"] for h in hourly[i:i + n] if h.get("pm2_5") is not None]
        pm = sum(vals) / len(vals) if vals else None
        level = aqi_math.pm25_level(pm)
        threshold = 2 if (act.sensitive or sensitive_household) else 3
        day = act.start[:10]
        same_day = [j for j, h in enumerate(hourly) if j >= now and h["time"].startswith(day)
                    and 6 <= int(h["time"][11:13]) <= 20 and h.get("pm2_5") is not None]
        best_j = min(same_day, key=lambda j: hourly[j]["pm2_5"]) if same_day else None
        label = aqi_math.CATEGORIES[level].label
        item = {"activity": act.title, "start": act.start, "who": act.who,
                "pm2_5": None if pm is None else round(pm, 1), "level": level, "category": label}
        if level >= threshold:
            alt = hourly[best_j] if best_j is not None else None
            better = alt is not None and alt["pm2_5"] < (pm or 0) * 0.8
            item["status"] = "warn"
            head = tr(lang, f"Forecast {label} air during '{act.title}'. ",
                      f"'{act.title}' के समय हवा {category(label, 'hi')} रहने का अनुमान है। ")
            if better:
                tail = tr(lang, f"Consider moving it to {fmt_hour(alt['time'])} (PM2.5 ≈ {alt['pm2_5']:.0f} vs "
                                f"{pm:.0f} µg/m³) or doing it indoors.",
                          f"इसे {fmt_hour(alt['time'], 'hi')} पर करें (PM2.5 ≈ {alt['pm2_5']:.0f} बनाम {pm:.0f} µg/m³) "
                          "या घर के अंदर करें।")
                item["suggested_time"] = alt["time"]
            else:
                tail = tr(lang, "Consider doing it indoors or shortening it.", "इसे घर के अंदर करें या समय कम रखें।")
            item["message"] = head + tail
        else:
            item["status"] = "ok"
            item["message"] = tr(lang, f"Air looks {label.lower()} for '{act.title}'.",
                                 f"'{act.title}' के लिए हवा {category(label, 'hi')} दिख रही है।")
        out.append(item)
    return {"alerts": out, "source": snapshot["source"], "observed_at": snapshot["observed_at"]}


def routine(household: Household, snapshot: dict[str, Any], commute_mode: str | None, lang: str = "en") -> dict[str, Any]:
    windows = snapshot.get("windows") or []
    today = windows[0] if windows else None
    best = today["best"]["start"] if today else None
    worst = today["worst"]["start"] if today else None
    level = max(snapshot["aqi"]["level"] or 0, today["worst"]["level"] if today else 0)
    has_kids = any(m.age_group in ("infant", "child") for m in household.members)
    has_elderly = any(m.age_group == "elderly" for m in household.members)
    exercisers = [m.name for m in household.members if m.exercises_outdoors]
    best_h = fmt_hour(best, lang)

    def step(time: str, en_title: str, hi_title: str, en: str, hi: str) -> dict[str, str]:
        return {"time": time, "title": tr(lang, en_title, hi_title), "detail": tr(lang, en, hi)}

    steps = [step("06:30", "Check today's air", "आज की हवा देखें",
                  "Open BreatheWise and check the cleanest window before planning outdoor time.",
                  "बाहर का समय तय करने से पहले BreatheWise में सबसे साफ़ समय देखें।")]
    if exercisers:
        names = ", ".join(exercisers)
        if level >= 4:
            en, hi = "Move exercise indoors (yoga, stretching, stairs).", "व्यायाम घर के अंदर करें (योग, स्ट्रेचिंग, सीढ़ियाँ)।"
        elif level >= 2:
            en, hi = f"Best outdoor slot today is around {best_h}.", f"आज बाहर का सबसे अच्छा समय {best_h} के आसपास है।"
        else:
            en, hi = "Air is fine — enjoy outdoor exercise.", "हवा ठीक है — बाहर व्यायाम का आनंद लें।"
        steps.append(step(best[11:16] if best and 2 <= level < 4 else "07:00",
                          f"Exercise ({names})", f"व्यायाम ({names})", en, hi))
    if commute_mode in ("car_petrol", "car_diesel", "car_cng", "car_ev", "two_wheeler"):
        steps.append(step("08:30", "Commute", "आना-जाना",
                          "Try bus/metro or carpool today; if driving, keep windows up with recirculation on and don't idle.",
                          "आज बस/मेट्रो या कारपूल आज़माएँ; गाड़ी चलाएँ तो खिड़कियाँ बंद, रीसर्कुलेशन चालू रखें और इंजन चालू छोड़कर न रुकें।"))
    elif commute_mode is None:
        steps.append(step("08:30", "Commute", "आना-जाना",
                          "If you travel today, metro, bus or carpooling cut emissions; prefer quieter streets and wear an "
                          "N95 if the air is Poor or worse.",
                          "आज कहीं जाएँ तो मेट्रो, बस या कारपूल से उत्सर्जन घटता है; कम ट्रैफ़िक वाली सड़कें चुनें और हवा ख़राब "
                          "हो तो N95 पहनें।"))
    else:
        steps.append(step("08:30", "Commute", "आना-जाना",
                          "Great low-emission choice. Prefer quieter streets; wear an N95 if air is Poor or worse.",
                          "कम उत्सर्जन वाला बढ़िया विकल्प। कम ट्रैफ़िक वाली सड़कें चुनें; हवा ख़राब हो तो N95 पहनें।"))
    if has_kids:
        steps.append(step(best[11:16] if best and level < 3 else "10:00", "Kids' outdoor play", "बच्चों का बाहर खेलना",
                          "Keep it indoors today." if level >= 3 else f"Schedule play around {best_h}.",
                          "आज घर के अंदर खिलाएँ।" if level >= 3 else f"खेल का समय {best_h} के आसपास रखें।"))
    steps.append(step(best[11:16] if best else "13:00", "Air out the home", "घर में हवा आने दें",
                      "Ventilate 10–15 min during the cleanest hour." if level <= 3 else
                      "Skip airing today; keep windows shut and run the purifier.",
                      "सबसे साफ़ घंटे में 10–15 मिनट खिड़कियाँ खोलें।" if level <= 3 else
                      "आज खिड़कियाँ न खोलें; बंद रखें और प्यूरीफायर चलाएँ।"))
    if has_elderly:
        steps.append(step("16:00", "Elders' walk", "बुज़ुर्गों की सैर",
                          "Walk indoors today." if level >= 3 else f"Short walk near {best_h}.",
                          "आज घर के अंदर टहलें।" if level >= 3 else f"{best_h} के आसपास थोड़ी सैर करें।"))
    steps.append(step(worst[11:16] if worst else "19:00", "Smog peak — stay in", "स्मॉग का चरम — घर में रहें",
                      "Windows closed, purifier on, no incense or frying without exhaust.",
                      "खिड़कियाँ बंद, प्यूरीफायर चालू, अगरबत्ती नहीं, और बिना एग्ज़ॉस्ट के तलना नहीं।"))
    steps.append(step("21:00", "Log eco-actions", "हरित कदम दर्ज करें",
                      "Record trips and habits in the Eco Tracker to see your weekly impact.",
                      "इको ट्रैकर में अपनी यात्राएँ और आदतें दर्ज करें और सप्ताह का असर देखें।"))
    steps.sort(key=lambda s: s["time"])
    return {"steps": steps, "air_level": level, "best_window": best, "worst_window": worst,
            "aqi": snapshot["aqi"], "source": snapshot["source"]}
