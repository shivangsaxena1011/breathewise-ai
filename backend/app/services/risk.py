"""Family Shield risk engine.

Deterministic and explainable: each member's risk = today's air level, raised
for sensitivity (age, conditions) and for exposure (time outdoors). Each action
carries a `why` so the UI can show the reasoning behind every recommendation.
All text is available in English and Hindi.
"""

from __future__ import annotations

from typing import Any

from ..schemas import Household, Member
from .i18n import fmt_hour, tr

RISK_LABELS = ["Low", "Low", "Moderate", "High", "Very high", "Extreme"]  # stable keys; the UI translates them
AGE_LABEL = {"infant": ("Infants", "शिशु"), "child": ("Children", "बच्चे"), "teen": ("Teenagers", "किशोर"),
             "adult": ("Adults", "वयस्क"), "elderly": ("Older adults", "बुज़ुर्ग")}
RESPIRATORY = {"asthma", "copd", "heart"}
CONDITION_HI = {"asthma": "अस्थमा", "copd": "COPD", "heart": "हृदय रोग"}


def _fmt_hour(iso: str | None, lang: str = "en") -> str:  # kept for callers that import it
    return fmt_hour(iso, lang)


def member_risk(member: Member, air_level: int, lang: str = "en") -> dict[str, Any]:
    factors: list[str] = []
    bonus = 0
    sensitive_age = member.age_group in ("infant", "child", "elderly")
    if sensitive_age:
        bonus += 1
        en, hi = AGE_LABEL[member.age_group]
        factors.append(tr(lang, f"{en} breathe more air per kg of body weight or have weaker defences, "
                                "so the same air affects them more.",
                          f"{hi} शरीर के वज़न के हिसाब से ज़्यादा हवा साँस में लेते हैं या उनकी रोग-प्रतिरोधक क्षमता कम होती है, "
                          "इसलिए वही हवा उन पर ज़्यादा असर करती है।"))
    resp = sorted(RESPIRATORY & set(member.conditions))
    if resp:
        if air_level >= 2:
            bonus += 1
        factors.append(tr(lang, f"Lung or heart conditions ({', '.join(resp)}) react to fine particles.",
                          f"फेफड़े या दिल की बीमारी ({', '.join(CONDITION_HI[c] for c in resp)}) पर सूक्ष्म कणों का असर होता है।"))
    if "diabetes" in member.conditions and air_level >= 3 and not resp:
        bonus += 1
        factors.append(tr(lang, "Diabetes raises the heart and blood-vessel strain caused by fine particles.",
                          "डायबिटीज़ में सूक्ष्म कणों से दिल और रक्त-नलिकाओं पर ज़्यादा दबाव पड़ता है।"))
    if "pregnant" in member.conditions:
        bonus += 0 if sensitive_age else 1
        factors.append(tr(lang, "Pregnancy: fine-particle exposure is linked to lower birth weight.",
                          "गर्भावस्था: सूक्ष्म कणों के संपर्क को जन्म के समय कम वज़न से जोड़ा गया है।"))
    if member.outdoor_hours >= 4 and air_level >= 2:
        bonus += 1
        factors.append(tr(lang, f"About {member.outdoor_hours:g} h outdoors a day means a much larger total dose.",
                          f"रोज़ लगभग {member.outdoor_hours:g} घंटे बाहर रहने से कुल प्रदूषण बहुत ज़्यादा शरीर में जाता है।"))
    score = min(5, air_level + bonus)
    return {"score": score, "label": RISK_LABELS[score], "factors": factors}


def member_actions(member: Member, air_level: int, risk: int, best: str | None, worst: str | None,
                   lang: str = "en") -> list[dict[str, str]]:
    acts: list[dict[str, str]] = []
    best_h, worst_h = fmt_hour(best, lang), fmt_hour(worst, lang)

    def add(en: str, hi: str, why_en: str, why_hi: str, priority: str = "medium") -> None:
        acts.append({"text": tr(lang, en, hi), "why": tr(lang, why_en, why_hi), "priority": priority})

    if member.exercises_outdoors or member.age_group in ("child", "teen"):
        if risk >= 4:
            add("Move exercise and play indoors today.", "आज व्यायाम और खेल घर के अंदर करें।",
                "Heavy breathing during exercise can pull 5–10× more polluted air deep into the lungs.",
                "व्यायाम में तेज़ साँस से 5–10 गुना ज़्यादा प्रदूषित हवा फेफड़ों में गहराई तक जाती है।", "high")
        elif risk >= 2:
            add(f"Keep outdoor exercise light and do it around {best_h}; avoid {worst_h}.",
                f"बाहर हल्का व्यायाम करें, {best_h} के आसपास; {worst_h} से बचें।",
                "The forecast shows the lowest PM2.5 in that window, so the same workout means a smaller dose.",
                "पूर्वानुमान में उसी समय PM2.5 सबसे कम है, इसलिए उतने ही व्यायाम में कम प्रदूषण शरीर में जाएगा।")
        else:
            add("Outdoor activity is fine today.", "आज बाहर गतिविधि ठीक है।",
                "Air quality is in the good-to-satisfactory range.", "हवा अच्छी से संतोषजनक श्रेणी में है।", "low")

    if air_level >= 3 and member.age_group != "infant":
        add("Wear a well-fitted N95/FFP2 mask outdoors (cloth and surgical masks do little against PM2.5).",
            "बाहर अच्छी तरह फिट N95/FFP2 मास्क पहनें (कपड़े और सर्जिकल मास्क PM2.5 से बहुत कम बचाते हैं)।",
            "N95 respirators filter most fine particles when they seal around the nose and chin.",
            "नाक और ठुड्डी पर ठीक से बैठने पर N95 ज़्यादातर सूक्ष्म कणों को रोक लेता है।",
            "high" if risk >= 4 else "medium")
    if member.age_group == "infant" and air_level >= 2:
        add("Keep the baby indoors in the cleanest room; do not use masks on infants.",
            "शिशु को घर के सबसे साफ़ कमरे में रखें; शिशुओं को मास्क न पहनाएँ।",
            "Masks are unsafe for infants; cutting exposure time is the safe protection.",
            "शिशुओं के लिए मास्क सुरक्षित नहीं हैं; प्रदूषण में कम समय बिताना ही सुरक्षित बचाव है।", "high")

    if RESPIRATORY & set(member.conditions):
        add("Keep reliever medicine handy and follow your doctor's action plan; seek care if symptoms escalate.",
            "राहत की दवा पास रखें और डॉक्टर की बताई योजना मानें; तकलीफ़ बढ़े तो तुरंत इलाज लें।",
            "Smog days commonly trigger asthma/COPD flare-ups and cardiac stress.",
            "स्मॉग वाले दिनों में अक्सर अस्थमा/COPD के दौरे और दिल पर दबाव बढ़ता है।", "high")

    if member.outdoor_hours >= 4 and air_level >= 2:
        add("Take breaks indoors or in a cleaner room, and stay away from roadside traffic where possible.",
            "बीच-बीच में घर के अंदर या साफ़ कमरे में आराम करें, और जहाँ हो सके सड़क के ट्रैफ़िक से दूर रहें।",
            "Long outdoor shifts dominate daily exposure; even short clean-air breaks lower the total dose.",
            "लंबे समय बाहर रहना ही सबसे ज़्यादा प्रदूषण देता है; छोटे-छोटे साफ़ हवा वाले ब्रेक भी कुल असर घटाते हैं।", "high")

    if member.age_group == "elderly" and air_level >= 2:
        add(f"Shift the morning walk to around {best_h}, or walk indoors (corridor, mall, home).",
            f"सुबह की सैर को {best_h} के आसपास करें, या घर के अंदर/गलियारे/मॉल में टहलें।",
            "Early mornings in winter often have trapped smog near the ground.",
            "सर्दियों की सुबह अक्सर स्मॉग ज़मीन के पास फँसा रहता है।")

    if member.commute_mode in ("two_wheeler", "e_two_wheeler", "cycle", "walk") and air_level >= 3:
        add("On a two-wheeler, cycle or foot: prefer side streets over main roads and wear the mask.",
            "दोपहिया, साइकिल या पैदल हों तो मुख्य सड़कों की बजाय अंदर की गलियाँ चुनें और मास्क पहनें।",
            "Concentrations next to heavy traffic can be far higher than the city average.",
            "भारी ट्रैफ़िक के पास प्रदूषण शहर के औसत से कहीं ज़्यादा हो सकता है।")

    if "pregnant" in member.conditions and air_level >= 2:
        add("Limit time outdoors during smog peaks and spend most time in the cleanest room.",
            "स्मॉग के चरम समय में बाहर कम जाएँ और ज़्यादातर समय सबसे साफ़ कमरे में बिताएँ।",
            "Reducing fine-particle exposure in pregnancy is a precaution recommended by health agencies.",
            "गर्भावस्था में सूक्ष्म कणों से बचाव स्वास्थ्य संस्थाओं द्वारा सुझाई गई सावधानी है।")
    return acts


def household_actions(household: Household, air_level: int, best: str | None, worst: str | None,
                      lang: str = "en") -> list[dict[str, str]]:
    home = household.home
    acts: list[dict[str, str]] = []
    best_h, worst_h = fmt_hour(best, lang), fmt_hour(worst, lang)

    def add(en: str, hi: str, why_en: str, why_hi: str, priority: str) -> None:
        acts.append({"text": tr(lang, en, hi), "why": tr(lang, why_en, why_hi), "priority": priority})

    if air_level >= 3:
        add(f"Keep windows closed, especially around {worst_h}. Air out briefly near {best_h}.",
            f"खिड़कियाँ बंद रखें, ख़ासकर {worst_h} के आसपास। {best_h} के पास थोड़ी देर हवा आने दें।",
            "Outdoor air is the main source of indoor PM2.5 on smog days.",
            "स्मॉग के दिनों में घर के अंदर का PM2.5 मुख्य रूप से बाहर की हवा से आता है।", "high")
    else:
        add(f"Ventilate the home around {best_h} for 15–20 minutes.",
            f"{best_h} के आसपास 15–20 मिनट घर में हवा आने दें।",
            "Fresh air removes cooking fumes and CO₂ while outdoor air is relatively clean.",
            "जब बाहर की हवा अपेक्षाकृत साफ़ हो, ताज़ी हवा खाना पकाने का धुआँ और CO₂ बाहर निकालती है।", "medium")
    if home.has_purifier:
        add("Run the purifier on high in the bedroom where the most sensitive person sleeps; keep the door closed.",
            "सबसे संवेदनशील व्यक्ति जिस कमरे में सोता है, वहाँ प्यूरीफायर तेज़ चलाएँ और दरवाज़ा बंद रखें।",
            "A purifier cleans one closed room well rather than a whole house poorly.",
            "प्यूरीफायर पूरे घर को थोड़ा-थोड़ा नहीं, एक बंद कमरे को अच्छी तरह साफ़ करता है।", "high")
    elif air_level >= 3:
        add("No purifier? A box fan with a MERV-13 filter taped to it makes a low-cost DIY air cleaner.",
            "प्यूरीफायर नहीं है? बॉक्स फैन पर MERV-13 फ़िल्टर टेप से लगाकर सस्ता घरेलू एयर क्लीनर बनाएँ।",
            "DIY fan-filter units have been shown to remove a large share of fine particles in a room.",
            "ऐसे घरेलू फैन-फ़िल्टर कमरे के सूक्ष्म कणों का बड़ा हिस्सा हटाते पाए गए हैं।", "medium")
    if home.cooking_fuel in ("biomass", "kerosene"):
        add("Cook with ventilation or outdoors-side doors open, and switch to LPG/induction if possible.",
            "खाना हवादार जगह पर या दरवाज़े खोलकर पकाएँ, और हो सके तो LPG/इंडक्शन अपनाएँ।",
            "Solid-fuel and kerosene cooking is one of the largest indoor pollution sources.",
            "लकड़ी/उपले और मिट्टी के तेल से खाना पकाना घर के अंदर प्रदूषण का सबसे बड़ा स्रोत है।", "high")
    if home.smoker_at_home:
        add("Keep the home smoke-free; smoke only outside, away from windows.",
            "घर को धुआँ-मुक्त रखें; धूम्रपान सिर्फ़ बाहर, खिड़कियों से दूर करें।",
            "Indoor smoking can raise PM2.5 more than a severe smog day outside.",
            "घर के अंदर धूम्रपान बाहर के गंभीर स्मॉग से भी ज़्यादा PM2.5 बढ़ा सकता है।", "high")
    if home.burns_incense and air_level >= 2:
        add("Skip incense, mosquito coils and candles on smog days.",
            "स्मॉग के दिनों में अगरबत्ती, मच्छर कॉइल और मोमबत्ती न जलाएँ।",
            "They release fine particles indoors exactly when you are sealing the home.",
            "जब घर बंद रखते हैं, ठीक तभी ये अंदर सूक्ष्म कण छोड़ते हैं।", "medium")
    add("Wet-mop floors and dust with a damp cloth instead of sweeping.",
        "झाड़ू की जगह गीला पोछा लगाएँ और गीले कपड़े से धूल साफ़ करें।",
        "Dry sweeping lifts settled dust back into the air you breathe.",
        "सूखी झाड़ू जमी हुई धूल को फिर से हवा में उड़ा देती है।", "low")
    add("Avoid idling vehicles and burning leaves or waste.",
        "गाड़ी खड़ी करके इंजन चालू न छोड़ें और पत्ते या कचरा न जलाएँ।",
        "These are direct local sources of the smog your family is breathing.",
        "आपका परिवार जो स्मॉग साँस में ले रहा है, ये उसके सीधे स्थानीय स्रोत हैं।", "low")
    return acts


def build_plan(household: Household, snapshot: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    level_now = snapshot["aqi"]["level"] or 0
    windows = snapshot.get("windows") or []
    today = windows[0] if windows else None
    best = today["best"]["start"] if today else None
    worst = today["worst"]["start"] if today else None
    air_level = max(level_now, today["worst"]["level"] if today else 0)

    members = []
    for m in household.members:
        r = member_risk(m, air_level, lang)
        members.append({
            "name": m.name,
            "age_group": m.age_group,
            "risk": r,
            "actions": member_actions(m, air_level, r["score"], best, worst, lang),
        })
    # Ties (e.g. everyone capped at 5) go to the member with more sensitivity factors.
    top = max(members, key=lambda x: (x["risk"]["score"], len(x["risk"]["factors"])))
    a = snapshot["aqi"]
    return {
        "air_level": air_level,
        "aqi": a,
        "best_window": best,
        "worst_window": worst,
        "household_risk": top["risk"]["label"],
        "most_at_risk": top["name"],
        "members": members,
        "household_actions": household_actions(household, air_level, best, worst, lang),
        "explanation": {
            "data_used": [
                tr(lang, f"Estimated AQI {a['value']} ({a['label']}) at {snapshot['observed_at']}",
                   f"अनुमानित AQI {a['value']} ({a['label']}), समय {snapshot['observed_at']}"),
                tr(lang, f"Cleanest 2-h window starts {fmt_hour(best)}; dirtiest {fmt_hour(worst)}",
                   f"सबसे साफ़ 2 घंटे {fmt_hour(best, 'hi')} से; सबसे ख़राब {fmt_hour(worst, 'hi')} से")
                if today else tr(lang, "No hourly forecast available", "घंटेवार पूर्वानुमान उपलब्ध नहीं"),
                tr(lang, "Household profile you entered (ages, conditions, time outdoors)",
                   "आपकी दी गई परिवार की जानकारी (आयु, स्वास्थ्य स्थिति, बाहर बिताया समय)"),
            ],
            "method": tr(lang, "Risk = today's worst air level (0–5), +1 for a sensitive age, +1 for lung/heart conditions "
                               "(or diabetes on Poor days), +1 for pregnancy, +1 for 4+ hours outdoors; capped at 5.",
                         "जोखिम = आज की सबसे ख़राब हवा का स्तर (0–5), संवेदनशील आयु पर +1, फेफड़े/दिल की बीमारी "
                         "(या ख़राब हवा में डायबिटीज़) पर +1, गर्भावस्था पर +1, 4+ घंटे बाहर रहने पर +1; अधिकतम 5।"),
            "reliability": tr(lang, "Air data is a regional model estimate (calibrated to a nearby station when one is "
                                    "available); actions follow general public-health guidance. Not a medical diagnosis.",
                              "हवा का डेटा क्षेत्रीय मॉडल अनुमान है (पास का स्टेशन हो तो उससे मिलाया गया); सुझाव सामान्य "
                              "जन-स्वास्थ्य मार्गदर्शन पर आधारित हैं। यह चिकित्सीय निदान नहीं है।"),
        },
        "source": snapshot["source"],
    }
