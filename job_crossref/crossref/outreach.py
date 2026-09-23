"""Review-only connection-note drafts. Nothing here sends anything.

Two modes:
  template - deterministic, free, offline
  claude   - Claude writes the notes (structured JSON), falling back to the template per note
             when a draft is missing, over the character limit, or the request is refused.
"""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

from .applications import search_name
from .models import Match
from .teams import functions_for

# One concrete hook per function bucket, pulled from the candidate background. Keep these short.
HOOKS = {
    "quant / data": "my time-series forecasting and factor-model work",
    "risk": "my VaR and tail-risk modeling work",
    "trade operations": "my Python data-pipeline work on position data",
    "investment banking": "my IB analyst work on B2B software deals",
    "investments / asset mgmt": "my portfolio analytics work",
    "equity research": "my equity valuation and comps work",
    "consulting / advisory": "my DCF/comps and strategy consulting work",
    "corporate finance / fp&a": "my modeling and valuation experience",
    "sales & trading": "my market-risk and factor-model work",
}

SCHOOL_LINE = {"stern": "fellow NYU Stern alum here (BS '26)", "nyu": "fellow NYU alum here (Stern '26)"}


def first_name(full_name: str) -> str:
    parts = re.sub(r"\(.*?\)", "", full_name).split()
    return parts[0].strip(",.") if parts else "there"


def short_role(role: str, max_len: int = 55) -> str:
    """'2027 Full-Time Analyst Program - Investments - Quantitative Investing' -> something note-sized."""
    r = re.sub(r"\b(?:R_?\d+|JR\d+|Req\.?\s*\d+|\d{5,})\b", "", role or "")
    r = re.sub(r"\b20\d\d\b|\bFull[- ]Time\b|\(.*?\)", "", r, flags=re.I)
    r = re.sub(r"\s{2,}", " ", r).strip()
    if len(r) > max_len:
        # Prefer cutting at a natural break (" - ", ", ", " & ") over mid-phrase.
        breaks = [m.start() for m in re.finditer(r"\s+[-–&]\s+|,\s+", r) if 12 <= m.start() <= max_len]
        r = r[:breaks[-1]] if breaks else r[:max_len].rsplit(" ", 1)[0]
    # Don't leave "... Corporate Finance &" or "... Intern - Summer" hanging after trimming.
    dangling = re.compile(r"(?:\s*[-–,&/]|\s+(?:and|of|for|the|summer|winter|fall|spring))\s*$", re.I)
    while dangling.search(r):
        r = dangling.sub("", r)
    return r.strip(" -–,&/")


def _hook(match: Match) -> str:
    for fn in match.shared_functions or sorted(functions_for(match.matched_role)):
        if fn in HOOKS:
            return HOOKS[fn]
    return ""


def _applied_phrase(role: str, company: str, applied_on: date | None, today: date) -> str:
    """'I just applied' only when it's true; older applications get honest phrasing."""
    target = f"the {role} role at {company}" if role else company
    verb = "for" if role else "to"
    if applied_on is None:
        return f"I applied {verb} {target}"
    age = (today - applied_on).days
    if age <= 21:
        return f"I just applied {verb} {target}"
    if age <= 90:
        return f"I recently applied {verb} {target}"
    when = f"{applied_on:%B}" if applied_on.year == today.year else f"{applied_on:%B %Y}"
    return f"Back in {when}, I applied {verb} {target}"


def template_note(match: Match, limit: int = 300, today: date | None = None) -> str:
    c = match.contact
    name = first_name(c.name)
    company = search_name(match.company)
    role = short_role(match.matched_role)
    applied = _applied_phrase(role, company, match.applied_on, today or date.today())
    school = SCHOOL_LINE.get(c.school, "recent NYU Stern grad here")
    hook = _hook(match)

    hi = f"Hi {name}, {school}. {applied}"
    if match.category == "Recruiter":
        variants = [
            f"{hi} and wanted to introduce myself, especially given {hook}. Would you be open to a quick 10-min chat "
            "about what the team looks for? Thanks so much, Rian" if hook else "",
            f"{hi} and wanted to introduce myself. Would you be open to a quick 10-min chat about what the team "
            "looks for? Thanks so much, Rian",
        ]
    elif match.category == "Same team":
        variants = [
            f"{hi} and saw you're on that team. Given {hook}, I'd love your take on it. Open to a quick 10-min "
            "call? Thanks so much, Rian" if hook else "",
            f"{hi} and saw you're on that team. I'd love your take on it. Open to a quick 10-min call? Thanks, Rian",
        ]
    else:
        variants = [
            f"{hi} and would love to hear how you've found the firm. Would you be open to a quick 10-min call? "
            "I'd really value your perspective. Thanks, Rian",
        ]
    variants.append(f"{hi}. Would you be open to a quick 10-min call to hear your take? Thanks, Rian")
    variants.append(f"Hi {name}, {school}. {_applied_phrase('', company, match.applied_on, today or date.today())}. "
                    "Open to a quick 10-min call? Thanks, Rian")
    for body in variants:
        if body and len(body) <= limit:
            return body
    return variants[-1][:limit]


# ---------------------------------------------------------------- Claude drafting (optional)

MODEL = "claude-opus-5"

SYSTEM = """You draft LinkedIn connection-request notes for Rian Sengupta, a May 2026 NYU Stern grad \
(BS in Business, Finance and Quantitative Economics) who's job hunting. Every recipient works at a company \
where Rian has an application in, and every recipient went to NYU or NYU Stern.

Write the way Rian writes: warm, polite, direct, and casual, using contractions, with no corporate filler and no \
gushing. Name the specific role he applied for without sounding transactional, tie in one concrete overlap \
between his background and the recipient's work when there's a real one, and close with a low-friction ask \
(a quick 10-minute call, or their take on the team). Sign off "Rian". Use only the facts given about the \
recipient. Each note must be at most {limit} characters including spaces.

Rian's background:
{background}"""


class Note(BaseModel):
    contact_id: str
    note: str


class NoteBatch(BaseModel):
    notes: list[Note]


def _describe(i: int, m: Match) -> str:
    c = m.contact
    return (
        f"contact_id: {i}\nname: {c.name}\nheadline: {c.headline or 'n/a'}\nschool: "
        f"{'NYU Stern' if c.school == 'stern' else 'NYU'}\ncompany: {search_name(m.company)}\n"
        f"role Rian applied for: {m.matched_role or 'n/a'}\n"
        f"applied on: {m.applied_on.isoformat() if m.applied_on else 'unknown'}\nrelationship: {m.category}"
    )


def claude_notes(matches: list[Match], background: str, limit: int = 300, batch_size: int = 15,
                 client=None, today: date | None = None) -> list[str]:
    """Draft notes with Claude. Returns one note per match, in order."""
    import anthropic

    client = client or anthropic.Anthropic()
    out = [template_note(m, limit, today) for m in matches]
    for start in range(0, len(matches), batch_size):
        batch = matches[start:start + batch_size]
        prompt = "Draft one note per contact.\n\n" + "\n\n".join(_describe(start + i, m) for i, m in enumerate(batch))
        try:
            response = client.beta.messages.parse(
                model=MODEL,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=SYSTEM.format(limit=limit, background=background.strip()),
                messages=[{"role": "user", "content": prompt}],
                output_format=NoteBatch,
            )
        except anthropic.APIStatusError as e:
            print(f"  Claude request failed ({e.status_code}); keeping template drafts for this batch")
            continue
        except anthropic.APIConnectionError:
            print("  Couldn't reach the Claude API; keeping template drafts for this batch")
            continue
        if response.stop_reason == "refusal" or response.parsed_output is None:
            continue
        for note in response.parsed_output.notes:
            idx = int(note.contact_id) if note.contact_id.isdigit() else -1
            text = note.note.strip()
            if start <= idx < start + len(batch) and 0 < len(text) <= limit:
                out[idx] = text
    return out
