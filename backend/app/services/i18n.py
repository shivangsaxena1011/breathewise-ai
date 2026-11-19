"""Tiny bilingual helpers for rule-based text (English / Hindi)."""

from __future__ import annotations

CATEGORY_HI = {"Good": "अच्छी", "Satisfactory": "संतोषजनक", "Moderate": "मध्यम", "Poor": "ख़राब",
               "Very Poor": "बहुत ख़राब", "Severe": "गंभीर"}


def tr(lang: str, en: str, hi: str) -> str:
    return hi if lang == "hi" else en


def fmt_hour(iso: str | None, lang: str = "en") -> str:
    """'7 AM' / 'सुबह 7 बजे'. Falls back to 'the cleanest hours' when no time is known."""
    if not iso:
        return tr(lang, "the cleanest hours", "सबसे साफ़ घंटों")
    h = int(iso[11:13])
    twelve = (h % 12) or 12
    if lang != "hi":
        return f"{twelve} {'AM' if h < 12 else 'PM'}"
    part = "सुबह" if 4 <= h < 12 else "दोपहर" if 12 <= h < 16 else "शाम" if 16 <= h < 20 else "रात"
    return f"{part} {twelve} बजे"


def category(label: str, lang: str) -> str:
    return CATEGORY_HI.get(label, label) if lang == "hi" else label
