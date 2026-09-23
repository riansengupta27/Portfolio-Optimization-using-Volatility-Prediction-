from __future__ import annotations

import json
import re
from pathlib import Path

from .applications import ascii_fold, normalize_company, search_name

# How big firms show up in LinkedIn headlines, keyed by normalize_company(<name in applications.csv>).
# Firm-specific extras for your own list go in data/aliases.json (gitignored), loaded with load_aliases().
ALIASES: dict[str, tuple[str, ...]] = {
    "jpmorgan chase": ("J.P. Morgan", "JPMorgan", "JPMorganChase", "JP Morgan"),
    "bank of america": ("BofA", "BofA Securities", "Merrill Lynch"),
    "goldman sachs": ("Goldman",),
    "citi": ("Citigroup", "Citibank"),
    "wells fargo": ("Wells Fargo Securities",),
    "morgan stanley": ("Morgan Stanley", "MSIM"),
    "bny": ("BNY Mellon", "BNY"),
    "state street": ("State Street Global Advisors", "SSGA"),
    "td securities": ("TD Securities", "TD Bank", "TD Cowen"),
    "bmo capital markets": ("BMO",),
    "rbc capital markets": ("RBC",),
    "citizens": ("Citizens Financial", "Citizens JMP", "Citizens Capital Markets"),
    "u s bank": ("U.S. Bank", "US Bank", "U.S. Bancorp"),
    "credit agricole cib": ("Crédit Agricole", "Credit Agricole", "CA-CIB", "CACIB"),
    "pwc": ("PricewaterhouseCoopers",),
    "ey parthenon": ("EY-Parthenon", "EY Parthenon", "Ernst & Young", "EY"),
    "mckinsey and company": ("McKinsey",),
    "boston consulting group": ("BCG",),
    "aqr capital management": ("AQR",),
    "point72": ("Cubist",),
    "man group": ("Man Group", "Man AHL", "Man Numeric"),
    "kkr": ("Kohlberg Kravis",),
    "nuveen": ("TIAA",),
    "new york life": ("New York Life", "NYL", "NYL Investors"),
}


def load_aliases(path: str | Path) -> None:
    """Merge extra aliases from JSON ({"Company as in applications.csv": ["Alias", ...]}) into ALIASES."""
    for company, names in json.loads(Path(path).read_text(encoding="utf-8")).items():
        key = normalize_company(company)
        ALIASES[key] = tuple(dict.fromkeys([*ALIASES.get(key, ()), *names]))


def _fold(text: str) -> str:
    """Lowercase, strip accents, and collapse punctuation so 'Crédit Agricole' == 'credit agricole'."""
    text = ascii_fold(text).lower().replace("&", " and ")
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", text).split()) + " "


def names_for(company: str) -> list[str]:
    key = normalize_company(company)
    names = [search_name(company)]
    names += [a for a in ALIASES.get(key, ()) if a not in names]
    return names


def mentions_company(text: str, company: str) -> bool:
    """Whole-word match of the company or one of its aliases inside free text."""
    haystack = _fold(text or "")
    for name in names_for(company):
        needle = _fold(name)
        if needle.strip() and needle in haystack:
            return True
    return False
