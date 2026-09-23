"""Paid source: an Apify LinkedIn people-search actor (no LinkedIn cookies, so no account risk).

Default actor is HarvestAPI's LinkedIn Profile Search. Actor input schemas change, so the input is a
JSON template you can override (--apify-input path.json). Placeholders: {company}, {company_url}.
Results are post-filtered for NYU/Stern here regardless of what the actor's own filters did.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from ..companies import mentions_company
from ..models import Contact
from ..schools import detect_school, school_from_education
from .serp import canonical_profile_url

DEFAULT_ACTOR = "harvestapi~linkedin-profile-search"
DEFAULT_INPUT = {
    "currentCompanies": ["{company_url}"],
    "schools": ["New York University", "NYU Stern School of Business"],
    "maxItems": 50,
    "profileScraperMode": "Short",
}


def _fill(template, company: str, company_url: str):
    if isinstance(template, str):
        return template.replace("{company_url}", company_url).replace("{company}", company)
    if isinstance(template, list):
        return [_fill(t, company, company_url) for t in template]
    if isinstance(template, dict):
        return {k: _fill(v, company, company_url) for k, v in template.items()}
    return template


def _first(item: dict, *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _education_strings(item: dict) -> list[str]:
    out = []
    for e in item.get("education") or item.get("educations") or []:
        if isinstance(e, dict):
            out.append(" ".join(str(e.get(k, "")) for k in ("schoolName", "school", "title", "degree", "fieldOfStudy")))
        elif isinstance(e, str):
            out.append(e)
    return out


def _current_company_strings(item: dict) -> list[str]:
    out = []
    positions = item.get("currentPosition") or item.get("currentPositions") or item.get("experience") or []
    if isinstance(positions, dict):
        positions = [positions]
    for p in positions:
        if isinstance(p, dict):
            out.append(" ".join(str(p.get(k, "")) for k in ("companyName", "company", "title", "position")))
    return out


def parse_item(item: dict, company: str) -> Contact | None:
    url = canonical_profile_url(_first(item, "linkedinUrl", "profileUrl", "url", "publicProfileUrl"))
    if not url and item.get("publicIdentifier"):
        url = f"https://www.linkedin.com/in/{item['publicIdentifier']}/"
    name = _first(item, "fullName", "name") or " ".join(
        x for x in (_first(item, "firstName"), _first(item, "lastName")) if x
    )
    headline = _first(item, "headline", "title", "position", "occupation")
    if not url or not name:
        return None
    school, evidence = school_from_education(_education_strings(item))
    if school is None:
        school, evidence = detect_school(headline)
    if school is None:
        return None
    current = _current_company_strings(item)
    return Contact(
        company=company,
        name=name,
        headline=headline,
        linkedin_url=url,
        school=school,
        school_evidence=evidence,
        source="apify",
        currently_at_company=any(mentions_company(c, company) for c in current) if current else None,
    )


def search_company(company: str, company_url: str = "", actor: str = DEFAULT_ACTOR,
                   input_template: str | Path | None = None, timeout: int = 300) -> list[Contact]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("Set APIFY_TOKEN to use the Apify source")
    template = json.loads(Path(input_template).read_text()) if input_template else DEFAULT_INPUT
    payload = _fill(template, company, company_url or company)
    r = requests.post(
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
        params={"token": token},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return [c for c in (parse_item(i, company) for i in r.json()) if c]
