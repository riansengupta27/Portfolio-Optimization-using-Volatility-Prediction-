# job_crossref

Cross-references the jobs you've applied to against LinkedIn and surfaces **NYU / NYU Stern** people at
those companies, flags who's on (or next to) the team you applied to, ranks them, and drafts
review-only connection notes. Nothing is ever sent automatically.

```
applications.csv ─► group by company, tag status (interviewing / active / stale / rejected)
                     │
      sources ───────┤  links   : NYU + Stern alumni-page and X-ray search URLs (free, you click)
                     │  manual  : contacts you (or a Claude session) found, as JSON
                     │  serp    : site:linkedin.com/in X-ray via SerpAPI or Brave (API key)
                     │  apify   : LinkedIn people-search actor with school filter (paid, API token)
                     ▼
      school check (Stern > NYU) ─► team match vs. your applied role ─► score ─► drafts ─► CSV / XLSX
```

All personal data lives in `data/` and results in `output/`. Both are gitignored, so they never land in this repo.

## Run it

```bash
cd job_crossref
pip install -r requirements.txt
python -m crossref --apps data/applications.csv --sources manual --manual data/hits.json \
                   --drafts-file data/drafts.json
```

Outputs: `output/contacts.csv`, `output/companies.csv`, `output/nyu_crossref.xlsx`.

### Inputs

`data/applications.csv`:

| column | example |
|---|---|
| company | `Globex Bank` |
| role | `Markets Operations Analyst` |
| date_applied | `2026-09-16` |
| status | `active` \| `interviewing` \| `rejected` \| `withdrawn` \| `closed` |
| source | `ats` \| `handshake` \| `linkedin` |
| notes | free text |

`active` applications older than `--stale-days` (default 90) are treated as `stale`.

`data/hits.json` (manual source): `[{"company", "name", "headline", "url", "school": "stern"|"nyu", "evidence", "current"}]`.
`company` must match the name in `applications.csv`.

`data/aliases.json` (optional): `{"<company as in applications.csv>": ["<how it shows up on LinkedIn>", ...]}`. Extra names for firms the built-in alias list doesn't cover, e.g. a parent brand or an abbreviation.

`data/drafts.json` (optional): `{"<linkedin url>": "<note>"}`. Hand-written notes override generated ones.

### Paid / keyed sources

| source | env var | notes |
|---|---|---|
| `serp` | `SERPAPI_API_KEY` (or `BRAVE_SEARCH_API_KEY` with `--serp-provider brave`) | one query per company; sees only what the search index shows |
| `apify` | `APIFY_TOKEN` | default actor `harvestapi~linkedin-profile-search`; field names in `DEFAULT_INPUT` weren't verified against the live schema, so check them on the actor page or pass `--apify-input your_input.json`. `--company-urls` maps company → LinkedIn company URL for the actor's company filter |
| `--drafts claude` | `ANTHROPIC_API_KEY` | Claude writes the notes as structured JSON; any note over `--note-limit` falls back to the template |

Example: `python -m crossref --sources manual,serp --min-status active`.

### Scoring

`school (Stern 3, NYU 2) + team match (0–3) + recruiter bonus (1.5) + application status (interviewing +2, active +1,
stale 0, rejected −1) ± current-employee signal`. Team match compares the contact's headline to your *live*
applications at that firm, using function buckets (risk, ECM/DCM, trade ops, quant, ...) plus shared words.
Company-name words don't count, and desk abbreviations (ECM, DCM, FIG, CHAM) are expanded.

### Caveats

- Search-derived contacts are leads, not facts. Rows whose school evidence says `verify` matched the query, but
  the snippet didn't show the school. LinkedIn's "People also viewed" sidebar can cause that.
- `currently_at_company = unconfirmed` means the company showed up on the page but not in the headline, so it may be a past job.
- LinkedIn invites cap notes at 300 characters on Premium and 200 on free accounts. Use `--note-limit 200` for free.

## Tests

```bash
python -m pytest -q
```
