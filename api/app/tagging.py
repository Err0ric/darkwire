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


def _keywords(*terms: str) -> re.Pattern[str]:
    """Like _words, but each term also matches with a plain s / es / ed suffix
    (breach, breaches, breached). Not stemming: list -ing, -ation and y/ies forms."""
    return _words(*(rf"(?:{t})(?:s|es|ed)?" for t in terms))


# Checked in this order against the title, then the first paragraph. First hit wins.
CATEGORY_RULES: list[tuple[Category, re.Pattern[str]]] = [
    (Category.vulnerability, _keywords(
        r"vulnerability", r"vulnerabilities", r"zero-day", r"0-day", r"flaw", r"exploit",
        r"exploiting", r"exploitation", r"RCE", r"remote code execution", r"patch", r"bug",
        r"security update", r"CVE-\d{4}-\d{4,7}", r"privilege escalation", r"authentication bypass",
    )),
    # Kept narrow: "exposed" or "compromised" in ordinary prose is not a breach.
    (Category.breach, _keywords(r"breach", r"data leak", r"leaked data", r"stolen data", r"hacked")),
    (Category.ransomware, _keywords(r"ransomware", r"extortion", r"LockBit", r"Akira", r"Cl0p", r"Black Basta")),
    (Category.advisory, _keywords(r"advisory", r"advisories", r"guidance", r"bulletin", r"alert", r"ICS")),
    (Category.research, _keywords(
        r"research", r"researcher", r"analysis", r"campaign", r"malware", r"threat actor", r"APT\d*",
        r"botnet", r"phishing", r"backdoor", r"trojan", r"infostealer", r"stealer",
    )),
]


def guess_category(title: str, excerpt: str, has_cve: bool) -> Category:
    """Title first. The first paragraph is only consulted when the title matches nothing."""
    for text in (title, excerpt):
        for category, pattern in CATEGORY_RULES:
            if pattern.search(text):
                return category
    return Category.vulnerability if has_cve else Category.news


AD_TEXT = _keywords(r"sponsored", r"sponsored by", r"partner content", r"webinar", r"virtual event")
AD_URL = re.compile(r"/(?:sponsored|partner-content|webinars?|events)(?:/|-|$)", re.IGNORECASE)


# Headline wording that means exploitation is already happening. Used to flag rows that
# have no CVE yet, so the row can still say so.
EXPLOITED = _keywords(r"zero-day", r"zero day", r"0-day", r"actively exploited", r"exploited in the wild", r"in the wild")
ZERO_DAY = _keywords(r"zero-day", r"zero day", r"0-day")


def says_exploited(title: str) -> bool:
    return bool(EXPLOITED.search(title))


def is_ad(title: str, url: str, excerpt: str) -> bool:
    """Sponsored posts, partner content, webinars and event promos."""
    return bool(AD_TEXT.search(title) or AD_URL.search(url) or AD_TEXT.search(excerpt))


@dataclass(frozen=True)
class _VendorPattern:
    vendor_id: int
    pattern: re.Pattern[str]


BODY_MIN_MENTIONS = 2


class VendorMatcher:
    """Aliases on word boundaries, case-insensitive.

    A title match wins: earliest match, longer alias on a tie (so "IOS XE" beats "iOS").
    With no title match, the first paragraph must mention a vendor at least twice;
    most mentions wins, then earliest.
    """

    def __init__(self, vendors: list[Vendor]):
        self._patterns = []
        # Per vendor: its product aliases (anything that is not just the vendor's name),
        # each matching a plain plural too ("NetScalers").
        self._products: dict[int, list[tuple[str, re.Pattern[str]]]] = {}
        for v in vendors:
            aliases = sorted({a for a in v.aliases if a}, key=len, reverse=True)
            if aliases:
                self._patterns.append(_VendorPattern(v.id, _words(*map(re.escape, aliases))))
            self._products[v.id] = [
                (a.lower(), _keywords(re.escape(a)))
                for a in aliases
                if a.lower() != v.name.lower() and not a.lower().startswith(v.name.lower() + " ")
            ]

    def products(self, vendor_id: int | None, title: str) -> set[str]:
        """Which of the vendor's product aliases the title mentions."""
        return {name for name, p in self._products.get(vendor_id or -1, []) if p.search(title)}

    def match(self, title: str, excerpt: str) -> int | None:
        best: tuple[int, int] | None = None
        best_id = None
        for p in self._patterns:
            m = p.pattern.search(title)
            if m:
                key = (m.start(), -len(m.group(0)))
                if best is None or key < best:
                    best, best_id = key, p.vendor_id
        if best_id is not None:
            return best_id

        for p in self._patterns:
            hits = list(p.pattern.finditer(excerpt))
            if len(hits) >= BODY_MIN_MENTIONS:
                key = (-len(hits), hits[0].start())
                if best is None or key < best:
                    best, best_id = key, p.vendor_id
        return best_id
