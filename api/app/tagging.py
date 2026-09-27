"""Text rules applied to each article on ingest: CVE IDs, category, vendor."""

import html
import re
from dataclasses import dataclass

from app.models import Category, Vendor

CVE_RE = re.compile(r"\bCVE-(\d{4})-(\d{4,7})\b", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_PARA_RE = re.compile(r"</p\s*>|<br\s*/?>\s*<br\s*/?>|\n\s*\n", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def clean_text(raw: str | None) -> str:
    """HTML to one line of plain text."""
    if not raw:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw))).strip()


def first_paragraph(raw: str | None, limit: int = 1000) -> str:
    if not raw:
        return ""
    for part in _PARA_RE.split(raw):
        text = clean_text(part)
        if text:
            return text[:limit]
    return ""


def extract_cves(*texts: str) -> list[str]:
    """CVE IDs in order of first appearance, normalized to upper case."""
    seen: dict[str, None] = {}
    for text in texts:
        for year, num in CVE_RE.findall(text or ""):
            seen.setdefault(f"CVE-{year}-{num}", None)
    return list(seen)


def _words(*terms: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)(?:" + "|".join(terms) + r")(?!\w)", re.IGNORECASE)


# Checked in this order against the title, then the first paragraph. First hit wins.
CATEGORY_RULES: list[tuple[Category, re.Pattern[str]]] = [
    (Category.vulnerability, _words(
        r"vulnerabilit(?:y|ies)", r"zero-days?", r"0-days?", r"flaws?", r"exploit(?:s|ed|ing|ation)?",
        r"RCE", r"remote code execution", r"patch(?:es|ed)?", r"bugs?", r"security updates?",
        r"CVE-\d{4}-\d{4,7}", r"privilege escalation", r"authentication bypass",
    )),
    (Category.breach, _words(
        r"breach(?:es|ed)?", r"data leaks?", r"leaked", r"stolen data", r"hacked", r"exposed",
        r"compromised", r"cyberattacks?", r"intrusion",
    )),
    (Category.ransomware, _words(r"ransomware", r"extortion", r"LockBit", r"Akira", r"Cl0p", r"Black Basta")),
    (Category.advisory, _words(r"advisor(?:y|ies)", r"guidance", r"bulletins?", r"alerts?", r"ICS")),
    (Category.research, _words(
        r"research(?:ers?)?", r"analysis", r"campaigns?", r"malware", r"threat actors?", r"APT\d*",
        r"botnets?", r"phishing", r"backdoors?", r"trojans?", r"infostealers?", r"stealers?",
    )),
]


def guess_category(title: str, excerpt: str, has_cve: bool) -> Category:
    for text in (title, excerpt):
        for category, pattern in CATEGORY_RULES:
            if pattern.search(text):
                return category
    return Category.vulnerability if has_cve else Category.news


@dataclass(frozen=True)
class _VendorPattern:
    vendor_id: int
    pattern: re.Pattern[str]


class VendorMatcher:
    """Aliases on word boundaries, case-insensitive. Title beats first paragraph,
    earlier match beats later, longer alias beats shorter (so "IOS XE" beats "iOS")."""

    def __init__(self, vendors: list[Vendor]):
        self._patterns = []
        for v in vendors:
            aliases = sorted({a for a in [v.name, *v.aliases] if a}, key=len, reverse=True)
            if aliases:
                self._patterns.append(_VendorPattern(v.id, _words(*map(re.escape, aliases))))

    def match(self, title: str, excerpt: str) -> int | None:
        best: tuple[int, int, int] | None = None
        best_id = None
        for field, text in enumerate((title, excerpt)):
            for p in self._patterns:
                m = p.pattern.search(text)
                if m:
                    key = (field, m.start(), -len(m.group(0)))
                    if best is None or key < best:
                        best, best_id = key, p.vendor_id
            if best_id is not None:
                return best_id
        return None
