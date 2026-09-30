"""What the articles state, read in the same Haiku call as the summary (app/summaries.py).

The call returns JSON (structured outputs): the summary text, checked by review_summary() as
before, and `facts`: whether the articles state in-the-wild exploitation or a public proof of
concept, the affected products / versions, and a fixed version. Every fact must come with a quote,
and verify() keeps a fact only when:

- its quote appears in the material the model was given (whitespace, case and quote marks
  aside), so nothing comes from the model's memory;
- for affected / fixed, the value itself appears in that quote;
- nothing in it is a URL or markdown, and it is short.

Anything else is dropped. Verified facts are stored in items.facts ({} when none held up) and are
only ever shown labeled "per article", after vendor, NVD and CISA data (CLAUDE.md, Summary model).
"""

import json
import re

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


def verify(facts: dict, material: str) -> dict:
    """The facts whose quotes are in the material (and whose values are in their quotes)."""
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
    return out
