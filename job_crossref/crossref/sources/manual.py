"""Import contacts found by hand (or by a Claude session's web search) from a JSON list.

Each item: {"company", "name", "headline", "url", "school": "stern"|"nyu", "evidence", "snippet", "current": bool|null}
`company` must match the company name used in applications.csv.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Contact
from ..schools import detect_school
from .serp import canonical_profile_url


def load_contacts(path: str | Path) -> list[Contact]:
    contacts = []
    for item in json.loads(Path(path).read_text(encoding="utf-8")):
        url = canonical_profile_url(item.get("url", ""))
        if not url or not item.get("name") or not item.get("company"):
            continue
        school = item.get("school")
        evidence = item.get("evidence", "")
        if school not in ("stern", "nyu"):
            school, evidence = detect_school(f"{item.get('headline', '')} {item.get('snippet', '')}")
        if school is None:
            continue
        contacts.append(
            Contact(
                company=item["company"],
                name=item["name"].strip(),
                headline=item.get("headline", "").strip(),
                linkedin_url=url,
                school=school,
                school_evidence=evidence,
                source=item.get("source", "manual"),
                snippet=item.get("snippet", ""),
                currently_at_company=item.get("current"),
            )
        )
    return contacts
