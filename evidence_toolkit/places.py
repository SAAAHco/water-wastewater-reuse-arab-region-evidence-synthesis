"""Heuristic place tags: the countries, cities and regions named in a passage.

The default gazetteer covers the 19 Arab countries of the Middle East and North Africa used in the review for which
this toolkit was written. Pass your own ``{tag: regular expression}`` mapping to ``tag_place`` for another region.
"""
from __future__ import annotations

import re

COUNTRY_PATTERNS: dict[str, str] = {
    "Algeria": r"Algeri|Algiers|Boumerd",
    "Bahrain": r"Bahrain|Manama",
    "Egypt": r"Egypt|Cairo|Nile|Alexandria|Fayoum|Nile Delta",
    "Iraq": r"Iraq|Baghdad|Basra",
    "Jordan": r"Jordan|Amman|Samra|Ramtha|Wadi Musa|Zarqa|Irbid|Aqaba|Mafraq|King Talal",
    "Kuwait": r"Kuwait|Sulaibiya",
    "Lebanon": r"Leban|Beirut|Bekaa|Beqaa|Zahl|Ablah|Litani",
    "Libya": r"Libya|Tripoli|Benghazi",
    "Mauritania": r"Mauritan|Nouakchott",
    "Morocco": r"Morocc|Marrakech|Rabat|Casablanca|Tangier|Agadir|Souss|Biougra",
    "Oman": r"\bOman|Muscat|Salalah",
    "Palestine": r"Palestin|West Bank|Gaza|Hebron|Jericho|Nablus|Ramallah|Jenin|Bethlehem",
    "Qatar": r"Qatar|Doha",
    "Saudi Arabia": r"Saudi|Riyadh|Jeddah|\bKSA\b|Assir|Asir|Ahsa|Hassa|Dammam",
    "Sudan": r"Sudan|Khartoum",
    "Syria": r"Syria|Damascus|Aleppo",
    "Tunisia": r"Tunis|Sfax|Sousse|Nabeul|Cap Bon|Souhil|Cebala|Hajeb|Mornag|Ouardanine",
    "UAE": r"\bUAE\b|Emirates|Abu Dhabi|Dubai|Sharjah|Al Ain|Wathba",
    "Yemen": r"Yemen|Sana|\bAden\b|Taiz",
    # neighbours that appear in the same literature, so that their evidence is not tagged to an Arab country by page context
    "Israel": r"Israel",
    "Iran": r"\bIran\b|Iranian|Tehran",
    "Turkey": r"Turkey|Turkish|Türkiye",
}
REGION_PATTERNS: dict[str, str] = {
    "MENA": r"\bMENA\b|Middle East and North Africa|Middle East|North Africa|Arab (?:region|world|countries|States)",
    "GCC": r"\bGCC\b|Gulf Cooperation Council|Gulf (?:states|countries|region)|Arabian Gulf|Persian Gulf",
    "Maghreb": r"Maghreb",
    "Mashreq": r"Mashreq|Mashriq",
    "Global": r"\bglobal(?:ly)?\b|\bworldwide\b|\bworld\b",
}
_COMPILED_C = {k: re.compile(v, re.I) for k, v in COUNTRY_PATTERNS.items()}
_COMPILED_R = {k: re.compile(v, re.I) for k, v in REGION_PATTERNS.items()}


def countries_in(text: str, patterns: dict[str, re.Pattern] | None = None) -> list[str]:
    pats = patterns or _COMPILED_C
    return [name for name, pat in pats.items() if pat.search(text or "")]


def tag_place(text: str, context: str = "") -> str:
    """Countries named in the passage; else regions named in it; else countries named on the page; else Unspecified."""
    found = countries_in(text)
    if found:
        return "; ".join(found)
    regions = [name for name, pat in _COMPILED_R.items() if pat.search(text or "")]
    if regions:
        return "Region: " + "; ".join(regions)
    in_context = countries_in(context)
    if in_context:
        return "Page context: " + "; ".join(in_context)
    return "Unspecified"
