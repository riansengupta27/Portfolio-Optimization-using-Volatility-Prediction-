from __future__ import annotations

import re

# Function buckets used to decide whether a contact sits on (or next to) the team you applied to.
# Order matters only for display; matching is set-based.
FUNCTIONS: dict[str, tuple[str, ...]] = {
    "investment banking": (
        "investment banking", "m&a", "mergers", "equity capital markets", "ecm", "debt capital markets", "dcm",
        "leveraged finance", "financial institutions group", "fig", "restructuring", "coverage", "investment banker",
        "global banking", "public finance",
    ),
    "sales & trading": ("trader", "trading desk", "sales & trading", "sales and trading", "market making", "global markets"),
    "trade operations": (
        "trade support", "trading services", "operations", "client operations", "corporate actions", "settlement",
        "middle office", "portfolio control", "asset administrator", "specialty asset", "fund administration",
    ),
    "quant / data": (
        "quantitative", "quant", "data scientist", "data science", "machine learning", "systematic", "time series",
        "analytics", "researcher",
    ),
    "risk": ("risk", "counterparty", "surveillance", "model validation", "compliance"),
    "equity research": ("equity research", "research analyst", "research associate"),
    "investments / asset mgmt": (
        "portfolio management", "portfolio manager", "asset management", "investment analyst", "investments",
        "private equity", "portfolio implementation", "performance attribution", "investment strategy",
        "fund flow", "asset-backed", "credit", "insurance", "k-star", "closely held", "portfolio valuation",
    ),
    "investor relations": ("investor relations",),
    "wealth management": ("wealth", "financial advisor", "financial representative", "financial professional", "private bank"),
    "consulting / advisory": (
        "consultant", "consulting", "strategy", "diligence", "transaction advisory", "valuation", "advisory",
    ),
    "corporate finance / fp&a": (
        "financial analyst", "fp&a", "revenue", "corporate development", "strategic finance", "finance leadership",
        "bizops", "treasury", "controller",
    ),
    "client services": ("client service", "institutional client", "relationship manager", "client advisor"),
    "product": ("product manager", "product associate", "product"),
    "business development": ("business development", "account executive", "sales representative"),
}

_RECRUITER = re.compile(
    r"recruit|talent acquisition|campus (?:recruit|program)|university relations|early careers?|early talent|"
    r"people partner|human resources|\bhr\b",
    re.I,
)

_STOPWORDS = {
    "analyst", "associate", "senior", "junior", "sr", "jr", "i", "ii", "iii", "vice", "president", "vp",
    "director", "managing", "md", "head", "of", "and", "the", "a", "at", "in", "for", "to", "new", "york",
    "program", "full", "time", "full-time", "2026", "2027", "summer", "winter", "fall", "intern", "internship",
    "cohort", "grad", "graduate", "college", "team", "group", "-", "&", "nyu", "stern", "university",
    # generic corporate filler that shows up in firm names ("Truist Securities", "TD Bank")
    "securities", "bank", "partners", "llc", "inc", "corp", "company",
}


def _contains(text: str, keyword: str) -> bool:
    # Word-boundary match so "ecm" doesn't hit "recommend" and "fig" doesn't hit "config".
    return re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text) is not None


def functions_for(text: str) -> set[str]:
    t = (text or "").lower()
    return {name for name, keywords in FUNCTIONS.items() if any(_contains(t, k) for k in keywords)}


# Expand desk abbreviations so "TMT ECM Analyst" overlaps with "Equity Capital Markets Analyst".
_ABBREVIATIONS = {
    "ecm": "equity capital markets", "dcm": "debt capital markets", "m&a": "mergers acquisitions",
    "fig": "financial institutions", "levfin": "leveraged finance", "fp&a": "financial planning analysis",
    "cham": "closely held asset management", "ir": "investor relations",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9&+]+", (text or "").lower())
    expanded = " ".join(_ABBREVIATIONS.get(w, w) for w in words).split()
    return {w for w in expanded if w not in _STOPWORDS and len(w) > 2}


def is_recruiter(title: str) -> bool:
    return bool(_RECRUITER.search(title or ""))


def team_overlap(role: str, title: str, company: str = "") -> tuple[int, list[str]]:
    """Score 0-3 for how close a contact's title is to the applied role.

    3 = shared function bucket and a shared distinctive word (e.g. both say "trading services")
    2 = shared function bucket
    1 = shared distinctive word only
    Words from the company name don't count ("Truist Securities" in both isn't a team match).
    """
    shared = sorted(functions_for(role) & functions_for(title))
    words = (_tokens(role) & _tokens(title)) - _tokens(company)
    if shared and words:
        return 3, shared
    if shared:
        return 2, shared
    if words:
        return 1, []
    return 0, []
