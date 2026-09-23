"""Zero-cost, zero-risk source: pre-filtered URLs you open yourself while logged in to LinkedIn."""
from __future__ import annotations

from urllib.parse import quote, quote_plus

from ..applications import search_name

# LinkedIn school page slugs. The school "People" tab filters alumni by a company keyword.
SCHOOL_SLUGS = {
    "NYU": "new-york-university",
    "NYU Stern": "nyu-stern-school-of-business",
}


def alumni_url(school_slug: str, company: str) -> str:
    return f"https://www.linkedin.com/school/{school_slug}/people/?keywords={quote(search_name(company))}"


def people_search_url(company: str, extra: str = "NYU") -> str:
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote(f"{search_name(company)} {extra}")


def xray_query(company: str, team_keyword: str | None = None) -> str:
    q = f'site:linkedin.com/in "{search_name(company)}" ("NYU Stern" OR "Stern School of Business" OR "New York University")'
    if team_keyword:
        q += f' "{team_keyword}"'
    return q


def google_xray_url(company: str, team_keyword: str | None = None) -> str:
    return "https://www.google.com/search?q=" + quote_plus(xray_query(company, team_keyword))


def links_for(company: str) -> dict[str, str]:
    return {
        "nyu_stern_alumni": alumni_url(SCHOOL_SLUGS["NYU Stern"], company),
        "nyu_alumni": alumni_url(SCHOOL_SLUGS["NYU"], company),
        "linkedin_search": people_search_url(company),
        "google_xray": google_xray_url(company),
    }
