from __future__ import annotations

from datetime import date

from .applications import STATUS_PRIORITY, CompanyApps, normalize_company
from .models import Contact, Match
from .teams import is_recruiter, team_overlap

SCHOOL_WEIGHT = {"stern": 3.0, "nyu": 2.0}
STATUS_BONUS = {"interviewing": 2.0, "active": 1.0, "stale": 0.0, "rejected": -1.0}


def dedupe(contacts: list[Contact]) -> list[Contact]:
    """One row per (company, profile). Keeps the strongest school tag and merges sources."""
    merged: dict[tuple[str, str], Contact] = {}
    for c in contacts:
        k = (normalize_company(c.company), c.linkedin_url)
        prev = merged.get(k)
        if prev is None:
            merged[k] = c
            continue
        if SCHOOL_WEIGHT.get(c.school, 0) > SCHOOL_WEIGHT.get(prev.school, 0):
            prev.school, prev.school_evidence = c.school, c.school_evidence
        if len(c.headline) > len(prev.headline):
            prev.headline = c.headline
        if prev.currently_at_company is None:
            prev.currently_at_company = c.currently_at_company
        if c.source not in prev.source.split("+"):
            prev.source = f"{prev.source}+{c.source}"
    return list(merged.values())


def best_role(group: CompanyApps, headline: str) -> tuple[str, int, list[str], date | None]:
    """The live applied role this contact's title is closest to (ties go to the fresher application)."""
    candidates = group.live_roles()
    if not candidates:
        return "", 0, [], group.latest_date
    scored = []
    for role, status, applied in candidates:
        score, shared = team_overlap(role, headline, group.name)
        scored.append((score, STATUS_PRIORITY.get(status, 0), applied or date.min, role, shared))
    score, _, applied, role, shared = max(scored, key=lambda t: (t[0], t[1], t[2]))
    return role, score, shared, None if applied == date.min else applied


def score_contact(contact: Contact, group: CompanyApps) -> Match:
    role, team_score, shared, applied_on = best_role(group, contact.headline)
    recruiter = is_recruiter(contact.headline)
    if recruiter:
        category = "Recruiter"
    elif team_score >= 2:
        category = "Same team"
    else:
        category = "Same company"

    score = SCHOOL_WEIGHT.get(contact.school, 0) + team_score
    score += 1.5 if recruiter else 0
    score += STATUS_BONUS.get(group.best_status, -2.0)
    if contact.currently_at_company is True:
        score += 0.5
    elif contact.currently_at_company is False:
        score -= 2.0  # alum of the firm, not a current employee
    return Match(
        company_key=group.key,
        company=group.name,
        contact=contact,
        category=category,
        matched_role=role,
        team_score=team_score,
        applied_on=applied_on,
        shared_functions=shared,
        score=round(score, 2),
    )


def build_matches(contacts: list[Contact], groups: dict[str, CompanyApps]) -> list[Match]:
    matches = []
    for contact in dedupe(contacts):
        group = groups.get(normalize_company(contact.company))
        if group is None:
            continue  # contact for a company you haven't applied to
        matches.append(score_contact(contact, group))
    return sorted(matches, key=lambda m: (-m.score, m.company, m.contact.name))
