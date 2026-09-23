import json
from datetime import date
from types import SimpleNamespace

import pytest

from crossref import companies
from crossref.__main__ import main
from crossref.applications import Application, group_by_company, normalize_company
from crossref.companies import ALIASES, mentions_company
from crossref.models import Contact
from crossref.outreach import NoteBatch, Note, claude_notes, short_role, template_note
from crossref.rank import build_matches
from crossref.schools import detect_school
from crossref.sources import apify, manual, serp
from crossref.sources.links import links_for
from crossref.teams import is_recruiter, team_overlap

# Fixtures use made-up firms and roles on purpose: this repo is public, so no real application data belongs here.
TODAY = date(2026, 9, 23)


def app(company, role="", status="active", d=date(2026, 9, 16)):
    return Application(company=company, role=role, date_applied=d, status=status)


def contact(company, name="Jane Doe", headline="", school="stern", current=True):
    return Contact(company=company, name=name, headline=headline,
                   linkedin_url=f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}/",
                   school=school, currently_at_company=current)


# ---------------------------------------------------------------- applications

@pytest.mark.parametrize("raw, key", [
    ("Doe O'Brien + Co.", "doe o brien"),
    ("Société Générale CIB", "societe generale cib"),
    ("Acme (Globex Holdings)", "acme"),
    ("Initech Capital Holdings, LLC", "initech capital holdings"),
    ("Hooli Trading", "hooli trading"),
])
def test_normalize_company(raw, key):
    assert normalize_company(raw) == key


def test_alias_keys_are_reachable():
    assert [k for k in ALIASES if normalize_company(k) != k] == []


def test_load_aliases_merges_by_normalized_name(tmp_path, monkeypatch):
    monkeypatch.setattr(companies, "ALIASES", dict(ALIASES))
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps({"Initech (Hooli Group)": ["Initech Labs"], "JPMorgan Chase": ["Chase"]}))
    companies.load_aliases(path)
    assert mentions_company("Analyst at Initech Labs", "Initech (Hooli Group)")
    assert mentions_company("Associate at Chase", "JPMorgan Chase")
    assert mentions_company("Associate at J.P. Morgan", "JPMorgan Chase")  # built-ins kept


def test_grouping_prefers_best_status_and_marks_stale():
    groups = group_by_company([
        app("Globex Bank", "Rates Analyst", "rejected", date(2026, 1, 16)),
        app("Globex Bank", "Markets Operations Analyst"),
        app("Initech", "", "active", date(2026, 2, 14)),
    ], TODAY)
    assert groups["globex bank"].best_status == "active"
    assert groups["globex bank"].latest_date == date(2026, 9, 16)
    assert groups["initech"].best_status == "stale"


# ---------------------------------------------------------------- schools / companies / teams

@pytest.mark.parametrize("text, tag", [
    ("Analyst at Acme | NYU Stern '24", "stern"),
    ("New York University Stern School of Business", "stern"),
    ("Leonard N. Stern School of Business", "stern"),
    ("Quant Researcher · New York University", "nyu"),
    ("MS Math, NYU Courant Institute", "nyu"),
    ("Nurse at NYU Langone Health", None),
    ("Howard Stern fan, Goldman Sachs", None),
    ("", None),
])
def test_detect_school(text, tag):
    assert detect_school(text)[0] == tag


def test_mentions_company_uses_aliases_and_word_boundaries():
    assert mentions_company("Analyst @ J.P. Morgan", "JPMorgan Chase")
    assert mentions_company("Associate at AQR Arbitrage", "AQR Capital Management")
    assert mentions_company("VP, Crédit Agricole CIB", "Crédit Agricole CIB")
    assert not mentions_company("Analyst at Goldman Sachs", "AQR Capital Management")
    assert not mentions_company("Hey there", "EY-Parthenon")  # "EY" alias must be a whole word


def test_team_overlap():
    assert team_overlap("Trade Support Analyst", "Analyst, Trade Support at Globex")[0] == 3
    assert team_overlap("Risk Analytics Analyst", "Market Risk Associate")[0] >= 2
    assert team_overlap("Investment Banking Analyst (Healthcare)", "Software Engineer")[0] == 0
    # "ecm" must not match inside "recommend"
    assert "investment banking" not in team_overlap("ECM Analyst", "I recommend products")[1]


def test_is_recruiter():
    assert is_recruiter("Campus Recruiting Lead at Globex")
    assert is_recruiter("Talent Acquisition Partner")
    assert not is_recruiter("Portfolio Manager")


# ---------------------------------------------------------------- sources

def test_serp_parse_result():
    c = serp.parse_result("Jane Doe - Analyst - Acme Capital Management | LinkedIn",
                          "https://www.linkedin.com/in/JaneDoe?trk=x", "NYU Stern School of Business · New York",
                          "Acme Capital Management")
    assert c.name == "Jane Doe" and c.school == "stern" and c.currently_at_company is True
    assert c.linkedin_url == "https://www.linkedin.com/in/janedoe/"


def test_serp_parse_rejects_non_profiles_and_wrong_company():
    assert serp.parse_result("Acme | LinkedIn", "https://www.linkedin.com/company/acme/", "NYU",
                             "Acme Capital Management") is None
    assert serp.parse_result("Jane Doe - Goldman Sachs | LinkedIn", "https://linkedin.com/in/jd", "NYU Stern",
                             "Acme Capital Management") is None


def test_serp_query_school_fallback():
    c = serp.parse_result("Pat Rivera - Acme Capital Management | LinkedIn", "https://www.linkedin.com/in/pat-rivera-21/",
                          "", "Acme Capital Management", query_school="stern")
    assert c.school == "stern" and "query" in c.school_evidence


def test_apify_parse_item():
    item = {
        "firstName": "Sam", "lastName": "Lee", "headline": "Associate",
        "linkedinUrl": "https://www.linkedin.com/in/samlee",
        "education": [{"schoolName": "New York University - Leonard N. Stern School of Business"}],
        "currentPosition": [{"companyName": "Globex", "position": "Associate"}],
    }
    c = apify.parse_item(item, "Globex")
    assert c.name == "Sam Lee" and c.school == "stern" and c.currently_at_company is True
    assert apify.parse_item({**item, "education": [{"schoolName": "Columbia"}]}, "Globex") is None


def test_apify_template_fill():
    filled = apify._fill(apify.DEFAULT_INPUT, "Globex", "https://www.linkedin.com/company/globex")
    assert filled["currentCompanies"] == ["https://www.linkedin.com/company/globex"]


def test_manual_load(tmp_path):
    path = tmp_path / "hits.json"
    path.write_text(json.dumps([
        {"company": "Globex", "name": "Sam Lee", "headline": "Associate at Globex",
         "url": "https://www.linkedin.com/in/samlee/", "school": "stern"},
        {"company": "Globex", "name": "No School", "headline": "Associate", "url": "https://www.linkedin.com/in/x/"},
        {"company": "Globex", "name": "Bad Url", "url": "https://example.com", "school": "nyu"},
    ]))
    assert [c.name for c in manual.load_contacts(path)] == ["Sam Lee"]


def test_links_are_encoded():
    links = links_for("Acme (Globex Holdings)")
    assert links["nyu_stern_alumni"].endswith("/people/?keywords=Acme")
    assert "site%3Alinkedin.com%2Fin" in links["google_xray"]


# ---------------------------------------------------------------- ranking

def test_build_matches_ranks_same_team_stern_first_and_drops_unknown_companies():
    groups = group_by_company([
        app("Globex Bank", "Trade Support Analyst"),
        app("Initech", "Analyst", "rejected"),
    ], TODAY)
    matches = build_matches([
        contact("Globex Bank", "Nyu Peer", "Analyst at Globex Bank", school="nyu"),
        contact("Globex Bank", "Stern Teammate", "Trade Support Analyst at Globex Bank"),
        contact("Globex Bank", "Stern Recruiter", "Campus Recruiting at Globex Bank"),
        contact("Initech", "Old Firm", "Analyst at Initech"),
        contact("Hooli", "Not Applied"),
    ], groups)
    names = [m.contact.name for m in matches]
    assert names[0] == "Stern Teammate" and matches[0].category == "Same team"
    assert "Not Applied" not in names
    assert {m.contact.name: m.category for m in matches}["Stern Recruiter"] == "Recruiter"
    assert names[-1] == "Old Firm"  # rejected application ranks last


def test_dedupe_keeps_stern_tag():
    groups = group_by_company([app("Globex", "Analyst")], TODAY)
    a = contact("Globex", "Sam Lee", "Associate at Globex", school="nyu")
    b = contact("Globex", "Sam Lee", "Associate, Insurance at Globex", school="stern")
    [m] = build_matches([a, b], groups)
    assert m.contact.school == "stern" and "Insurance" in m.contact.headline


# ---------------------------------------------------------------- outreach

def _match(role, headline, company="Globex Bank", school="stern"):
    groups = group_by_company([app(company, role)], TODAY)
    return build_matches([contact(company, "Alex Kim", headline, school=school)], groups)[0]


@pytest.mark.parametrize("limit", [200, 300])
def test_template_note_respects_limit(limit):
    m = _match("Private Client Trust Administration Specialty Asset Administrator Analyst",
               "Specialty Asset Administrator, Private Client Trusts at Globex Bank")
    note = template_note(m, limit)
    assert len(note) <= limit and note.startswith("Hi Alex") and "Rian" in note


def test_short_role():
    assert short_role("2027 Full-Time Analyst Program - Investments (Req 12345)") == "Analyst Program - Investments"
    assert len(short_role("x " * 80)) <= 55


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(response):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(response)))


def test_claude_notes_uses_valid_drafts_and_falls_back_on_long_ones():
    m1 = _match("Trade Support Analyst", "Trade Support at Globex Bank")
    m2 = _match("Trade Support Analyst", "Analyst at Globex Bank")
    parsed = NoteBatch(notes=[Note(contact_id="0", note="Hi Alex, short note. Rian"), Note(contact_id="1", note="x" * 400)])
    client = fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    notes = claude_notes([m1, m2], "background", limit=300, client=client)
    assert notes[0] == "Hi Alex, short note. Rian"
    assert notes[1] == template_note(m2, 300)
    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5" and call["fallbacks"] == "default"
    assert call["output_format"] is NoteBatch


def test_claude_notes_refusal_keeps_templates():
    m = _match("Trade Support Analyst", "Trade Support at Globex Bank")
    client = fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    assert claude_notes([m], "bg", client=client) == [template_note(m, 300)]


# ---------------------------------------------------------------- CLI end to end

def test_cli_end_to_end(tmp_path):
    apps = tmp_path / "applications.csv"
    apps.write_text(
        "company,role,date_applied,status,source,notes\n"
        "Acme Capital Management,Portfolio Analytics Analyst,2026-09-23,active,ats,\n"
        "Initech,Analyst,2026-09-16,rejected,ats,\n"
    )
    hits = tmp_path / "hits.json"
    hits.write_text(json.dumps([{"company": "Acme Capital Management", "name": "Pat Rivera",
                                 "headline": "Portfolio Analytics at Acme Capital Management",
                                 "url": "https://www.linkedin.com/in/pat-rivera-21/", "school": "stern", "current": True}]))
    out = tmp_path / "out"
    main(["--apps", str(apps), "--manual", str(hits), "--aliases", str(tmp_path / "none.json"),
          "--out", str(out), "--today", "2026-09-23"])
    contacts = (out / "contacts.csv").read_text()
    assert "Pat Rivera" in contacts and "Same team" in contacts
    companies_csv = (out / "companies.csv").read_text().splitlines()
    assert companies_csv[1].startswith("Acme Capital Management,active")
    assert (out / "nyu_crossref.xlsx").exists()


def test_team_overlap_ignores_company_words_and_expands_abbreviations():
    assert team_overlap("2026 Globex Securities - Public Finance Analyst Program",
                        "TMT ECM Analyst II, Globex Securities", "Globex")[0] == 2
    assert team_overlap("Equity Capital Markets Analyst", "TMT ECM Analyst II, Globex Securities", "Globex")[0] == 3


def test_best_role_skips_rejected_applications():
    groups = group_by_company([
        app("Globex Securities", "Credit Risk Summer Analyst", "rejected"),
        app("Globex Securities", "Analyst, Investment Banking - Technology"),
    ], TODAY)
    [m] = build_matches([contact("Globex Securities", "Sam Lee", "Associate at Globex Securities (IB Credit, Technology)")],
                        groups)
    assert m.matched_role == "Analyst, Investment Banking - Technology"


def test_best_role_prefers_active_over_stale_on_ties():
    groups = group_by_company([
        app("Globex", "2026 Globex Securities - Public Finance Analyst Program", "active", date(2026, 2, 18)),
        app("Globex", "Equity Capital Markets Analyst"),
    ], TODAY)
    [m] = build_matches([contact("Globex", "Casey Morgan", "TMT ECM Analyst II, Globex Securities")], groups)
    assert m.matched_role == "Equity Capital Markets Analyst" and m.category == "Same team"


def test_private_banker_is_not_investment_banking():
    assert team_overlap("Financial Institutions Group - Analyst", "Senior Private Banker, Globex", "Globex")[0] == 0


def test_short_role_drops_dangling_words():
    assert short_role("2026 Associate Consultant - Business Valuation & Restructuring") == \
        "Associate Consultant - Business Valuation"
    assert short_role("Transaction Services - Due Diligence Intern - Summer 2027") == \
        "Transaction Services - Due Diligence Intern"


@pytest.mark.parametrize("applied, phrase", [
    (date(2026, 9, 16), "I just applied for"),
    (date(2026, 7, 14), "I recently applied for"),
    (date(2026, 2, 18), "Back in February, I applied for"),
    (date(2025, 10, 21), "Back in October 2025, I applied for"),
])
def test_template_note_is_honest_about_when_you_applied(applied, phrase):
    groups = group_by_company([app("Globex", "2027 Full-Time Analyst - Insurance Solutions", "active", applied)], TODAY)
    [m] = build_matches([contact("Globex", "Sam Lee", "Associate at Globex")], groups)
    assert phrase in template_note(m, 300, TODAY)


def test_short_role_cuts_at_natural_breaks():
    assert short_role("Data Scientist - Consumer Fraud Risk Management & Data Analytics") == \
        "Data Scientist - Consumer Fraud Risk Management"
    assert short_role("Graduate Associate, Corporate Strategy, Transaction Advisory Services") == \
        "Graduate Associate, Corporate Strategy"
