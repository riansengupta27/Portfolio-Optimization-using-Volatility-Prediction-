from __future__ import annotations

import re

# "Stern" alone is a common surname, so every Stern pattern needs NYU / "School of Business" context.
_STERN = re.compile(
    r"\bnyu[\s\-–—|,:]*stern\b|\bstern school of business\b|\bleonard n\.? stern\b|\bstern\s*\(nyu\)|\bstern,?\s+nyu\b",
    re.I,
)
_NYU = re.compile(
    r"\bnew york university\b|\bnyu\b(?!\s+langone)|\bcourant institute\b|\btandon school\b|\bgallatin school\b",
    re.I,
)
# Working at NYU's hospital system says nothing about where someone studied.
_EMPLOYER_ONLY = re.compile(r"\bnyu langone\b|\blangone health\b", re.I)


def detect_school(text: str) -> tuple[str | None, str]:
    """Return ("stern" | "nyu" | None, evidence snippet) for free text such as a headline or search snippet."""
    if not text:
        return None, ""
    m = _STERN.search(text)
    if m:
        return "stern", m.group(0)
    scrubbed = _EMPLOYER_ONLY.sub(" ", text)
    m = _NYU.search(scrubbed)
    if m:
        return "nyu", m.group(0)
    return None, ""


def school_from_education(entries: list[str]) -> tuple[str | None, str]:
    """Best tag across structured education entries (Stern beats plain NYU)."""
    best: tuple[str | None, str] = (None, "")
    for entry in entries:
        tag, evidence = detect_school(entry)
        if tag == "stern":
            return tag, evidence
        if tag == "nyu" and best[0] is None:
            best = (tag, evidence)
    return best
