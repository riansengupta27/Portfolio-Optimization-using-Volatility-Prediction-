"""CLI: python -m crossref --apps data/applications.csv --sources manual --manual data/hits.json"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from . import export, outreach
from .applications import STATUS_PRIORITY, group_by_company, load_applications
from .companies import load_aliases
from .rank import build_matches
from .sources import apify, manual, serp
from .sources.serp import canonical_profile_url


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Find NYU / NYU Stern people at companies you've applied to.")
    p.add_argument("--apps", default="data/applications.csv", help="applications CSV")
    p.add_argument("--sources", default="manual", help="comma list of: manual, serp, apify")
    p.add_argument("--manual", default="data/hits.json", help="JSON contacts for the manual source")
    p.add_argument("--aliases", default="data/aliases.json", help="optional JSON of extra company aliases")
    p.add_argument("--serp-provider", default="serpapi", choices=sorted(serp.PROVIDERS))
    p.add_argument("--apify-input", help="JSON input template for the Apify actor")
    p.add_argument("--apify-actor", default=apify.DEFAULT_ACTOR)
    p.add_argument("--company-urls", help="CSV of company,linkedin_company_url for Apify's company filter")
    p.add_argument("--min-status", default="stale", choices=["interviewing", "active", "stale", "rejected"],
                   help="only search companies whose best application status is at least this")
    p.add_argument("--stale-days", type=int, default=90, help="active apps older than this count as stale")
    p.add_argument("--today", default=date.today().isoformat())
    p.add_argument("--drafts", default="template", choices=["none", "template", "claude"])
    p.add_argument("--background", default="data/background.txt", help="your background, for Claude drafts")
    p.add_argument("--note-limit", type=int, default=300, help="300 for LinkedIn Premium, 200 for free accounts")
    p.add_argument("--top-per-company", type=int, default=2, help="draft notes for this many contacts per company")
    p.add_argument("--drafts-file", help="JSON {linkedin_url: note} of hand-written notes that override generated drafts")
    p.add_argument("--out", default="output")
    args = p.parse_args(argv)

    if Path(args.aliases).exists():
        load_aliases(args.aliases)
    today = date.fromisoformat(args.today)
    groups = group_by_company(load_applications(args.apps), today, args.stale_days)
    floor = STATUS_PRIORITY[args.min_status]
    targets = [g for g in groups.values() if g.priority >= floor]
    print(f"{len(groups)} companies from {args.apps}; searching {len(targets)} (status >= {args.min_status})")

    company_urls = {}
    if args.company_urls:
        with open(args.company_urls, newline="") as f:
            company_urls = {r["company"]: r["linkedin_company_url"] for r in csv.DictReader(f)}

    contacts = []
    for source in [s.strip() for s in args.sources.split(",") if s.strip()]:
        if source == "manual":
            if Path(args.manual).exists():
                contacts += manual.load_contacts(args.manual)
            else:
                print(f"  manual: {args.manual} not found, skipping")
        elif source in ("serp", "apify"):
            for g in targets:
                try:
                    if source == "serp":
                        found = serp.search_company(g.name, provider=args.serp_provider)
                    else:
                        found = apify.search_company(g.name, company_urls.get(g.name, ""), args.apify_actor,
                                                     args.apify_input)
                except Exception as e:  # one bad company shouldn't sink the run
                    print(f"  {source}: {g.name}: {e}")
                    continue
                print(f"  {source}: {g.name}: {len(found)} NYU/Stern hits")
                contacts += found
        else:
            p.error(f"unknown source {source!r}")

    matches = build_matches(contacts, groups)
    print(f"{len(matches)} NYU/Stern contacts across {len({m.company_key for m in matches})} companies")

    if args.drafts != "none":
        per_company: dict[str, int] = {}
        to_draft = []
        for m in matches:  # already sorted best-first
            if per_company.get(m.company_key, 0) < args.top_per_company:
                per_company[m.company_key] = per_company.get(m.company_key, 0) + 1
                to_draft.append(m)
        if args.drafts == "claude":
            background = Path(args.background).read_text() if Path(args.background).exists() else ""
            notes = outreach.claude_notes(to_draft, background, args.note_limit, today=today)
        else:
            notes = [outreach.template_note(m, args.note_limit, today) for m in to_draft]
        for m, note in zip(to_draft, notes):
            m.draft_note = note

    if args.drafts_file:
        overrides = {canonical_profile_url(u): n for u, n in json.loads(Path(args.drafts_file).read_text()).items()}
        for m in matches:
            note = overrides.get(m.contact.linkedin_url)
            if note:
                if len(note) > args.note_limit:
                    print(f"  warning: hand-written note for {m.contact.name} is {len(note)} chars (> {args.note_limit})")
                m.draft_note = note

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    contacts_rows = export.contact_rows(matches, groups)
    company_rows = export.company_rows(matches, groups)
    export.write_csv(out / "contacts.csv", contacts_rows, export.CONTACT_COLUMNS)
    export.write_csv(out / "companies.csv", company_rows, export.COMPANY_COLUMNS)
    wrote_xlsx = export.write_xlsx(out / "nyu_crossref.xlsx", {
        "Contacts": (contacts_rows, export.CONTACT_COLUMNS),
        "Companies": (company_rows, export.COMPANY_COLUMNS),
    })
    print(f"Wrote {out}/contacts.csv, {out}/companies.csv" + (f", {out}/nyu_crossref.xlsx" if wrote_xlsx else ""))


if __name__ == "__main__":
    main()
