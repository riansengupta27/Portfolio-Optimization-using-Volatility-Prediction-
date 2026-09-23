from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .models import Application

# Higher = more worth networking on right now.
STATUS_PRIORITY = {"interviewing": 4, "active": 3, "stale": 2, "rejected": 1, "withdrawn": 0, "closed": 0}

_LEGAL_SUFFIXES = {
    "inc", "llc", "lp", "llp", "ltd", "corp", "corporation", "co", "plc", "pc", "sa", "ag", "na",
}


def ascii_fold(text: str) -> str:
    """'Crédit Agricole' -> 'Credit Agricole'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def normalize_company(name: str) -> str:
    """Stable key for grouping: lowercase, no accents, parentheticals, punctuation, or trailing legal suffixes."""
    s = re.sub(r"\(.*?\)", " ", ascii_fold(name)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    tokens = s.split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def search_name(name: str) -> str:
    """Name to put in search queries: drop parentheticals like '(Morgan Stanley)'."""
    return re.sub(r"\s*\(.*?\)\s*", " ", name).strip()


def load_applications(path: str | Path) -> list[Application]:
    apps = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw_date = (row.get("date_applied") or "").strip()
            apps.append(
                Application(
                    company=row["company"].strip(),
                    role=(row.get("role") or "").strip(),
                    date_applied=date.fromisoformat(raw_date) if raw_date else None,
                    status=(row.get("status") or "active").strip().lower(),
                    source=(row.get("source") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return apps


def effective_status(app: Application, today: date, stale_days: int) -> str:
    """An 'active' application with no reply after `stale_days` is treated as stale."""
    if app.status == "active" and app.date_applied and (today - app.date_applied).days > stale_days:
        return "stale"
    return app.status


@dataclass
class CompanyApps:
    key: str
    name: str
    applications: list[Application] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)  # effective status, aligned with applications
    best_status: str = "closed"
    latest_date: date | None = None

    @property
    def priority(self) -> int:
        return STATUS_PRIORITY.get(self.best_status, 0)

    @property
    def roles(self) -> list[str]:
        return [a.role for a in self.applications if a.role]

    def live_roles(self) -> list[tuple[str, str, date | None]]:
        """(role, status, date) worth networking on: open applications first, dead ones only as a fallback."""
        pairs = [(a.role, s, a.date_applied) for a, s in zip(self.applications, self.statuses) if a.role]
        live = [p for p in pairs if STATUS_PRIORITY.get(p[1], 0) >= STATUS_PRIORITY["stale"]]
        return live or pairs


def group_by_company(apps: list[Application], today: date, stale_days: int = 90) -> dict[str, CompanyApps]:
    groups: dict[str, CompanyApps] = {}
    for app in apps:
        key = normalize_company(app.company)
        group = groups.setdefault(key, CompanyApps(key=key, name=app.company))
        group.applications.append(app)
        status = effective_status(app, today, stale_days)
        group.statuses.append(status)
        if STATUS_PRIORITY.get(status, 0) > STATUS_PRIORITY.get(group.best_status, 0):
            group.best_status = status
        if app.date_applied and (group.latest_date is None or app.date_applied > group.latest_date):
            group.latest_date = app.date_applied
    return groups
