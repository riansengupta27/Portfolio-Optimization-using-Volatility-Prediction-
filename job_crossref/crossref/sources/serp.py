"""Search-engine X-ray source: site:linkedin.com/in queries via SerpAPI or Brave Search.

Never touches linkedin.com directly, so there's no account or ban risk. It only sees what the
search index shows (name, headline, snippet), so school and current-employer tags need a manual check.
"""
from __future__ import annotations

import os
import re

import requests

from ..companies import mentions_company
from ..models import Contact
from ..schools import detect_school
from .links import xray_query

_TITLE_SUFFIX = re.compile(r"\s*[|\-–—]\s*LinkedIn\s*$", re.I)
_TITLE_SPLIT = re.compile(r"\s+[-–—|]\s+")
_PROFILE_URL = re.compile(r"https?://(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com/in/([^/?#]+)", re.I)


def canonical_profile_url(url: str) -> str | None:
    m = _PROFILE_URL.match(url or "")
    return f"https://www.linkedin.com/in/{m.group(1).lower()}/" if m else None


def parse_result(title: str, url: str, snippet: str, company: str, source: str = "serp",
                 query_school: str | None = None) -> Contact | None:
    """Turn one search hit into a Contact, or None if it isn't a LinkedIn profile for this company.

    `query_school` is the school the query was restricted to ("stern"/"nyu"); used as a fallback tag
    when the snippet doesn't show the school text (the page matched, the snippet just didn't include it).
    """
    profile = canonical_profile_url(url)
    if not profile:
        return None
    clean = _TITLE_SUFFIX.sub("", title or "").strip()
    parts = _TITLE_SPLIT.split(clean, maxsplit=1)
    name = parts[0].split(",")[0].strip()  # drop ", CFA" style suffixes
    headline = parts[1].strip() if len(parts) > 1 else ""
    if not name:
        return None

    text = f"{headline} {snippet}"
    if not mentions_company(text, company):
        return None
    school, evidence = detect_school(text)
    if school is None and query_school:
        school, evidence = query_school, "matched search query (school not shown in snippet)"
    if school is None:
        return None
    return Contact(
        company=company,
        name=name,
        headline=headline,
        linkedin_url=profile,
        school=school,
        school_evidence=evidence,
        source=source,
        snippet=snippet or "",
        # LinkedIn result titles carry the current employer; a snippet-only mention may be a past job.
        currently_at_company=True if mentions_company(headline, company) else None,
    )


def _serpapi(query: str, api_key: str, num: int) -> list[tuple[str, str, str]]:
    r = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "num": num, "api_key": api_key},
        timeout=30,
    )
    r.raise_for_status()
    return [(i.get("title", ""), i.get("link", ""), i.get("snippet", "")) for i in r.json().get("organic_results", [])]


def _brave(query: str, api_key: str, num: int) -> list[tuple[str, str, str]]:
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": min(num, 20)},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return [(i.get("title", ""), i.get("url", ""), i.get("description", "")) for i in r.json().get("web", {}).get("results", [])]


PROVIDERS = {"serpapi": ("SERPAPI_API_KEY", _serpapi), "brave": ("BRAVE_SEARCH_API_KEY", _brave)}


def search_company(company: str, provider: str = "serpapi", team_keywords: list[str] | None = None,
                   num: int = 20) -> list[Contact]:
    env_var, fetch = PROVIDERS[provider]
    api_key = os.environ.get(env_var)
    if not api_key:
        raise RuntimeError(f"Set {env_var} to use the '{provider}' search provider")
    contacts: list[Contact] = []
    for kw in [None, *(team_keywords or [])]:
        for title, url, snippet in fetch(xray_query(company, kw), api_key, num):
            contact = parse_result(title, url, snippet, company, source=f"serp:{provider}")
            if contact:
                contacts.append(contact)
    return contacts
