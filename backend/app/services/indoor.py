"""Indoor Air Doctor: ventilation verdict, room-by-room tips, purifier sizing (English / Hindi)."""

from __future__ import annotations

from typing import Any

from ..schemas import Home, Room
from .i18n import tr

TARGET_ACH = 5  # clean-air changes per hour commonly recommended for a room purifier
M3H_TO_CFM = 0.5886

# (text_en, text_hi, why_en, why_hi)
Tip = tuple[str, str, str, str]

ROOM_TIPS: dict[str, list[Tip]] = {
    "kitchen": [
        ("Run the exhaust fan/chimney while cooking and for 10 minutes after.",
         "खाना बनाते समय और उसके 10 मिनट बाद तक एग्ज़ॉस्ट फैन/चिमनी चलाएँ।",
         "Frying and high-heat cooking create PM2.5 spikes that can exceed outdoor smog levels.",
         "तलने और तेज़ आँच पर पकाने से PM2.5 अचानक बढ़ता है, जो बाहर के स्मॉग से भी ज़्यादा हो सकता है।"),
        ("Use lids, and prefer boiling/steaming to deep frying on smog days.",
         "ढक्कन लगाकर पकाएँ, और स्मॉग के दिनों में तलने की बजाय उबालना/भाप में पकाना चुनें।",
         "Less smoke and oil aerosol is produced in the first place.",
         "इससे शुरू से ही कम धुआँ और तेल के कण बनते हैं।"),
    ],
    "bedroom": [
        ("Make this the cleanest room: door closed, purifier or DIY filter running at night.",
         "इसे सबसे साफ़ कमरा बनाएँ: दरवाज़ा बंद, रात में प्यूरीफायर या घरेलू फ़िल्टर चालू।",
         "You spend ~8 hours here, so it gives the biggest exposure reduction.",
         "आप यहाँ लगभग 8 घंटे बिताते हैं, इसलिए यहीं सबसे ज़्यादा बचाव होता है।"),
        ("Wash bedding weekly in hot water.", "हर सप्ताह बिस्तर गर्म पानी में धोएँ।",
         "Removes settled dust and allergens.", "जमी धूल और एलर्जी पैदा करने वाले कण हटते हैं।"),
    ],
    "living": [
        ("Wet-mop floors; vacuum only with a HEPA vacuum.", "फ़र्श पर गीला पोछा लगाएँ; वैक्यूम सिर्फ़ HEPA वाला इस्तेमाल करें।",
         "Dry sweeping re-suspends fine dust.", "सूखी झाड़ू महीन धूल को फिर हवा में उड़ा देती है।"),
        ("No incense, coils or candles while windows are closed.", "खिड़कियाँ बंद हों तो अगरबत्ती, कॉइल या मोमबत्ती न जलाएँ।",
         "They are hidden indoor PM2.5 sources.", "ये घर के अंदर PM2.5 के छिपे स्रोत हैं।"),
    ],
    "kids": [
        ("Put the purifier where children nap/play; keep toys and floor dust-free.",
         "प्यूरीफायर वहाँ रखें जहाँ बच्चे सोते/खेलते हैं; खिलौने और फ़र्श धूल-मुक्त रखें।",
         "Children breathe faster and spend more time near the floor.",
         "बच्चे तेज़ साँस लेते हैं और ज़्यादा समय फ़र्श के पास रहते हैं।"),
    ],
    "study": [
        ("Crack the window or run the fan during clean hours to keep CO₂ down.",
         "साफ़ हवा वाले घंटों में खिड़की थोड़ी खोलें या पंखा चलाएँ ताकि CO₂ कम रहे।",
         "A sealed small room builds up CO₂, which causes drowsiness and headaches.",
         "बंद छोटे कमरे में CO₂ बढ़ता है, जिससे नींद आना और सिरदर्द होता है।"),
    ],
    "bathroom": [
        ("Use the exhaust fan after showers.", "नहाने के बाद एग्ज़ॉस्ट फैन चलाएँ।",
         "Prevents damp and mould, another indoor irritant.", "इससे नमी और फफूँद नहीं बनती, जो घर में जलन पैदा करती है।"),
    ],
}

FUEL_TIPS: dict[str, Tip] = {
    "biomass": ("Biomass (wood/dung) cooking: improve ventilation and move towards LPG/induction when possible.",
                "लकड़ी/उपले से खाना बनता है: हवा का रास्ता बेहतर करें और जब हो सके LPG/इंडक्शन अपनाएँ।",
                "Solid-fuel smoke is one of the largest health risks from indoor air in India.",
                "भारत में घर के अंदर की हवा से सबसे बड़े स्वास्थ्य जोखिमों में से एक ठोस ईंधन का धुआँ है।"),
    "kerosene": ("Replace kerosene stoves/lamps where possible; ventilate when using them.",
                 "जहाँ हो सके मिट्टी के तेल के स्टोव/लैंप बदलें; इस्तेमाल करते समय हवा आने दें।",
                 "Kerosene releases fine particles and gases indoors.",
                 "मिट्टी का तेल घर के अंदर सूक्ष्म कण और गैसें छोड़ता है।"),
}


def _tip(t: Tip, lang: str) -> dict[str, str]:
    return {"text": tr(lang, t[0], t[1]), "why": tr(lang, t[2], t[3])}


def ventilation_verdict(snapshot: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    level = snapshot["aqi"]["level"] or 0
    now = snapshot["hourly"][snapshot["now_index"]] if snapshot["hourly"] else {}
    now_level = now.get("level", level)
    windows = snapshot.get("windows") or []
    best = windows[0]["best"] if windows else None
    if now_level <= 1 and level >= 3:
        verdict, en, hi = ("brief", "Cleaner than the day's average right now — air out for 5–10 minutes, then close up.",
                           "अभी हवा दिन के औसत से साफ़ है — 5–10 मिनट खिड़कियाँ खोलें, फिर बंद कर दें।")
    elif now_level <= 1:
        verdict, en, hi = ("open", "Outdoor air is relatively clean now — open windows for 15–20 minutes.",
                           "अभी बाहर की हवा अपेक्षाकृत साफ़ है — 15–20 मिनट खिड़कियाँ खोलें।")
    elif now_level == 2:
        verdict, en, hi = ("brief", "Moderate outside — short cross-ventilation (5–10 min) is fine; avoid long airing.",
                           "बाहर हवा मध्यम है — थोड़ी देर (5–10 मिनट) हवा आने दें; लंबे समय तक न खोलें।")
    else:
        verdict, en, hi = ("closed", "Keep windows closed now: outdoor air is dirtier than well-sealed indoor air.",
                           "अभी खिड़कियाँ बंद रखें: बाहर की हवा बंद घर की हवा से ज़्यादा गंदी है।")
    return {
        "verdict": verdict,
        "text": tr(lang, en, hi),
        "now_pm2_5": now.get("pm2_5"),
        "best_window": best,
        "why": tr(lang, "Opening windows exchanges indoor air with outdoor air; that helps only when outdoor PM2.5 is lower "
                        "than what builds up indoors (cooking, dust).",
                  "खिड़की खोलने से अंदर-बाहर की हवा बदलती है; यह तभी फ़ायदेमंद है जब बाहर का PM2.5 घर में बनने वाले "
                  "प्रदूषण (खाना पकाना, धूल) से कम हो।"),
    }


def purifier_size(room: Room, lang: str = "en") -> dict[str, Any]:
    volume = room.area_m2 * room.height_m
    cadr_m3h = volume * TARGET_ACH
    return {
        "volume_m3": round(volume, 1),
        "cadr_m3h": round(cadr_m3h),
        "cadr_cfm": round(cadr_m3h * M3H_TO_CFM),
        "basis": tr(lang, f"{room.area_m2:g} m² × {room.height_m:g} m × {TARGET_ACH} air changes/hour",
                    f"{room.area_m2:g} m² × {room.height_m:g} m × {TARGET_ACH} बार हवा बदलना/घंटा"),
    }


def diagnose(home: Home, rooms: list[Room], snapshot: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    level = snapshot["aqi"]["level"] or 0
    out_rooms = []
    for room in rooms:
        tips = [_tip(t, lang) for t in ROOM_TIPS.get(room.kind, [])]
        if room.kind == "kitchen" and home.cooking_fuel in FUEL_TIPS:
            tips.insert(0, _tip(FUEL_TIPS[home.cooking_fuel], lang))
        out_rooms.append({"kind": room.kind, "tips": tips, "purifier": purifier_size(room, lang)})

    general: list[dict[str, str]] = []

    def add(en: str, hi: str, why_en: str, why_hi: str) -> None:
        general.append(_tip((en, hi, why_en, why_hi), lang))

    if home.smoker_at_home:
        add("Make the home smoke-free.", "घर को धुआँ-मुक्त बनाएँ।",
            "Indoor tobacco smoke is a major PM2.5 source.", "घर के अंदर तंबाकू का धुआँ PM2.5 का बड़ा स्रोत है।")
    if home.has_pets:
        add("Groom pets outdoors-side and vacuum with HEPA.", "पालतू जानवरों की सफ़ाई बाहर की ओर करें और HEPA वैक्यूम चलाएँ।",
            "Reduces dander and allergens.", "इससे रूसी और एलर्जी के कण कम होते हैं।")
    if home.has_purifier:
        add("Check the filter: replace HEPA every 6–12 months (sooner in heavy smog).",
            "फ़िल्टर जाँचें: HEPA हर 6–12 महीने में बदलें (भारी स्मॉग में जल्दी)।",
            "A clogged filter sharply reduces clean-air delivery.", "भरा हुआ फ़िल्टर साफ़ हवा देने की क्षमता बहुत घटा देता है।")
    else:
        add("Low-cost option: tape a MERV-13 filter to a box fan (DIY air cleaner).",
            "सस्ता उपाय: बॉक्स फैन पर MERV-13 फ़िल्टर टेप से लगाएँ (घरेलू एयर क्लीनर)।",
            "A well-built fan-filter unit can deliver clean air comparable to budget purifiers.",
            "अच्छी तरह बना फैन-फ़िल्टर सस्ते प्यूरीफायर जितनी साफ़ हवा दे सकता है।")
    if level >= 3:
        add("Seal obvious gaps around windows/doors with tape or draught strips.",
            "खिड़की/दरवाज़ों की दरारें टेप या पट्टियों से बंद करें।",
            "Less infiltration of smog when windows are closed.", "खिड़कियाँ बंद होने पर स्मॉग कम अंदर आता है।")
    add("Want to know your actual indoor level? A low-cost PM2.5 sensor helps verify these steps.",
        "घर के अंदर का असली स्तर जानना है? एक सस्ता PM2.5 सेंसर इन कदमों का असर जाँचने में मदद करता है।",
        "Indoor levels vary hugely between homes; measuring beats guessing.",
        "हर घर में अंदर का स्तर बहुत अलग होता है; अनुमान से बेहतर है नापना।")
    return {"ventilation": ventilation_verdict(snapshot, lang), "rooms": out_rooms, "general": general,
            "aqi": snapshot["aqi"], "source": snapshot["source"]}
