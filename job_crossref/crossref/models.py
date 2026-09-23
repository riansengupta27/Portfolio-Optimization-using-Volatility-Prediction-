from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Application:
    company: str
    role: str
    date_applied: date | None
    status: str  # active | interviewing | rejected | withdrawn | closed
    source: str = ""
    notes: str = ""


@dataclass
class Contact:
    company: str  # company as searched (display name from applications.csv)
    name: str
    headline: str
    linkedin_url: str
    school: str | None  # "stern" | "nyu" | None
    school_evidence: str = ""
    source: str = ""  # serp | apify | manual
    snippet: str = ""
    currently_at_company: bool | None = None  # None = unconfirmed


@dataclass
class Match:
    company_key: str
    company: str
    contact: Contact
    category: str  # "Same team" | "Recruiter" | "Same company"
    matched_role: str
    team_score: int
    applied_on: date | None = None
    shared_functions: list[str] = field(default_factory=list)
    score: float = 0.0
    draft_note: str = ""
