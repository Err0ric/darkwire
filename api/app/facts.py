"""What the articles state, read in the same Haiku call as the summary (app/summaries.py).

The call returns JSON (structured outputs): the summary text, checked by review_summary() as
before, and `facts`: whether the articles state in-the-wild exploitation or a public proof of
concept, the affected products / versions, and a fixed version. Every fact must come with a quote,
and verify() keeps a fact only when:

- its quote appears in the material the model was given (whitespace, case and quote marks
  aside), so nothing comes from the model's memory;
- for affected / fixed, the value itself appears in that quote;
- nothing in it is a URL or markdown, and it is short;
- and it says the right kind of thing (recheck): a public PoC quote says a PoC or exploit is
  public (published, released, public, available, GitHub, posted), is not negated, and if it
  names CVEs, names the row's displayed one; a fixed version is version-like, not a date or a product name alone; an
  affected value is a product or platform, not people, customer counts or organizations.
  In-the-wild exploitation is stored but not displayed anywhere.

Anything else is dropped. Verified facts are stored in items.facts ({} when none held up) and are
only ever shown labeled "per article", after vendor, NVD and CISA data (CLAUDE.md, Summary model).
"""

import json
import re

from app import versions

MAX_QUOTE = 400
MAX_VALUE = 160

PROMPT = """

Output format: reply with a JSON object with two keys. Every rule above applies to the "summary" value.
"summary": the summary text described above, or exactly SKIP.
"facts": what the articles themselves state, each with "quote", one sentence copied word for word from the articles that states it, or null:
- "exploited_in_wild": "stated" true only if the articles say attackers are exploiting it in the wild.
- "public_poc": "stated" true only if the articles say a proof-of-concept or exploit code is public.
- "affected": "text", the affected products and versions as the articles name them (short), or null.
- "fixed": "version", the fixed version as the articles name it, or null.
Use only what the articles say. When a fact is not stated, set stated to false or the value to null, and the quote to null."""

_NULLABLE = {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _flag() -> dict:
    return {
        "type": "object",
        "properties": {"stated": {"type": "boolean"}, "quote": _NULLABLE},
        "required": ["stated", "quote"],
        "additionalProperties": False,
    }


def _value(name: str) -> dict:
    return {
        "type": "object",
        "properties": {name: _NULLABLE, "quote": _NULLABLE},
        "required": [name, "quote"],
        "additionalProperties": False,
    }


SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "facts": {
            "type": "object",
            "properties": {
                "exploited_in_wild": _flag(),
                "public_poc": _flag(),
                "affected": _value("text"),
                "fixed": _value("version"),
            },
            "required": ["exploited_in_wild", "public_poc", "affected", "fixed"],
            "additionalProperties": False,
        },
    },
    "required": ["summary", "facts"],
    "additionalProperties": False,
}

OUTPUT_CONFIG = {"format": {"type": "json_schema", "schema": SCHEMA}}

_BAD = re.compile(r"(?i)https?://|www\.|\]\(|`|\*\*")


def _norm(text: str) -> str:
    text = re.sub(r"[‘’“”\"'`]", "", text or "")
    return " ".join(text.lower().split())


def parse(raw: str | None) -> tuple[str | None, dict]:
    """(summary text for review_summary, raw facts) from the model's JSON; (None, {}) when the
    output is not the expected JSON."""
    try:
        data = json.loads(raw or "")
    except ValueError:
        return None, {}
    if not isinstance(data, dict):
        return None, {}
    facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    summary = data.get("summary") if isinstance(data.get("summary"), str) else None
    return summary, facts


def _quote_ok(quote, material: str) -> bool:
    return (
        isinstance(quote, str)
        and 20 <= len(quote.strip()) <= MAX_QUOTE
        and not _BAD.search(quote)
        and _norm(quote) in _norm(material)
    )


# ---- what each fact must say (recheck(); also applied to facts already stored)

_POC = re.compile(r"proof[- ]of[- ]concept|\bpocs?\b|\bexploits?\b(?!-)", re.I)
_PUBLIC = re.compile(r"\b(publish(es|ed)?|releas(e|es|ed)|public(ly)?|available|github|posted)\b", re.I)
_NEGATION = re.compile(r"\b(no longer|not|never|didn'?t|did not|doesn'?t|isn'?t|wasn'?t|patched before)\b|n't\b", re.I)
_CVE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
# At least major.minor, or a build / release number, or a KB: "OpenPLC v4" and "version 7" are not.
_VERSION = re.compile(r"\d+\.\d+|\b(build|release|rev(ision)?)\s*\d+\b|\bKB\d{6,}\b", re.I)
# A web domain or website is not software: "Radaris.com and a dozen other domains".
_WEB = re.compile(r"\b[a-z0-9-]+\.(com|org|net|io|gov|edu|info|co|us|uk|de)\b|\b(domains?|websites?|web sites?|web pages?)\b", re.I)
_MONTH = re.compile(
    r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(tember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b",
    re.I,
)
# Who or how many, not what: people and customer counts, organization types, sectors.
_NOT_PRODUCT = re.compile(
    r"\b(\d[\d,.]*\s*(million|billion|thousand)?|dozens?|hundreds?|thousands?)\s+(\w+\s+){0,2}"
    r"(people|individuals|persons|customers?|users|patients|employees|accounts|records|victims|organi[sz]ations|companies|firms)\b"
    r"|\b(organi[sz]ations|universities|institutions|governments?|agencies|contractors|nonprofits|companies|firms|entities"
    r"|sectors?|industr(y|ies)|hospitals|schools|customers?|customer base|individuals|people|developers|victims)\b",
    re.I,
)


def poc_problem(quote: str, row_cve: str | None) -> str | None:
    """Why a public-PoC quote does not hold, or None: it must say a PoC / exploit is public, carry
    no negation, and if it names CVEs, one must be the row's displayed CVE (a quote about a
    sibling CVE the row also holds does not count). A quote naming no CVE stands on its article."""
    if not _POC.search(quote):
        return "no PoC or exploit named"
    if not _PUBLIC.search(quote):
        return "does not say it is public"
    if _NEGATION.search(quote):
        return "negated"
    named = {c.upper() for c in _CVE.findall(quote)}
    if named and row_cve and row_cve.upper() not in named:
        return f"about another CVE ({', '.join(sorted(named))})"
    return None


def fixed_problem(value: str) -> str | None:
    if not _VERSION.search(value):
        return "not a version"
    if _MONTH.search(value) and not re.search(r"\d+\.\d+", value):
        return "a date, not a version"
    return None


def affected_problem(value: str) -> str | None:
    if _NOT_PRODUCT.search(value):
        return "people, customers or organizations, not a product"
    if _WEB.search(value):
        return "web domains or sites, not a product"
    return None


def consistency(kept: dict) -> tuple[dict, list[tuple[str, str]]]:
    """A fixed version inside the affected range (versions.conflict): both go, unless the quotes
    name separate release branches and the fix gives one version per branch, which is kept with
    its branches ({"version", "branch"}) for display line by line."""
    affected, fixed = kept.get("affected"), kept.get("fixed")
    if not affected or not fixed or not versions.conflict(affected.get("text", ""), fixed.get("version", "")):
        return kept, []
    quotes = f"{fixed.get('quote', '')} {affected.get('quote', '')}"
    per_branch = versions.branches(fixed.get("version", ""), quotes) if versions.BRANCH.search(quotes) else []
    if per_branch:
        return {**kept, "fixed": {**fixed, "branches": per_branch}}, []
    why = "fixed version inside the affected range"
    return {k: v for k, v in kept.items() if k not in ("affected", "fixed")}, [("affected", why), ("fixed", why)]


def recheck(found: dict, row_cve: str | None = None) -> tuple[dict, list[tuple[str, str]]]:
    """(kept, removed as (fact, reason)) under the content rules, for facts already verified
    against their article. Exploited-in-the-wild is kept as is (not displayed anywhere)."""
    kept: dict = {}
    removed: list[tuple[str, str]] = []
    for key, fact in (found or {}).items():
        if key == "public_poc":
            why = poc_problem(fact.get("quote", ""), row_cve)
        elif key == "fixed":
            why = fixed_problem(fact.get("version", ""))
        elif key == "affected":
            why = affected_problem(fact.get("text", ""))
        else:
            why = None
        if why:
            removed.append((key, why))
        else:
            kept[key] = fact
    kept, dropped = consistency(kept)
    return kept, removed + dropped


def verify(facts: dict, material: str, row_cve: str | None = None) -> dict:
    """The facts whose quotes are in the material (and whose values are in their quotes), and
    that pass the content rules (recheck)."""
    out: dict = {}
    for key in ("exploited_in_wild", "public_poc"):
        f = facts.get(key) or {}
        if f.get("stated") is True and _quote_ok(f.get("quote"), material):
            out[key] = {"quote": f["quote"].strip()}
    for key, name in (("affected", "text"), ("fixed", "version")):
        f = facts.get(key) or {}
        value = f.get(name)
        if (
            isinstance(value, str)
            and 1 <= len(value.strip()) <= MAX_VALUE
            and not _BAD.search(value)
            and "\n" not in value
            and _quote_ok(f.get("quote"), material)
            and _norm(value) in _norm(f["quote"])
        ):
            out[key] = {name: value.strip(), "quote": f["quote"].strip()}
    return recheck(out, row_cve)[0]
