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


_COUNT = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_COUNTED = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+(?:[\w-]+\s+){0,4}?"
    r"(?:zero-days?|0-days?|flaws?|vulnerabilit(?:y|ies)|bugs?|cves?|issues?|weaknesses)\b",
    re.IGNORECASE,
)
SMALL_LIST = 3
_EXPLOITED = re.compile(
    r"\b(?:zero-days?|0-days?|exploit(?:ed|ing|s)?|in the wild|KEV|Known Exploited)\b", re.IGNORECASE
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def headline_cves(title: str, lead: str, *rest: str) -> list[str]:
    """The CVE IDs an article ties to its headline's issue, not every ID it mentions.

    Articles about one bulletin often list all of it ("the six other flaws ...") and older
    CVEs for context. In order: IDs in the title; everything when the article names three or
    fewer; IDs in the lead paragraph unless it lists a whole bulletin; the first N when the
    headline counts them ("Two ... Zero-Days"); for exploitation headlines, the IDs in
    sentences about exploitation; IDs mentioned more than once; else the first one."""
    in_title = extract_cves(title)
    if in_title:
        return in_title
    everything = extract_cves(lead, *rest)
    if len(everything) <= SMALL_LIST:
        return everything
    in_lead = extract_cves(lead)
    # A lead that enumerates a whole bulletin ("eight new vulnerabilities: CVE-..., ...") is
    # context, not the headline's issue.
    if in_lead and len(in_lead) <= SMALL_LIST:
        return in_lead
    counted = _COUNTED.search(title or "")
    if counted:
        word = counted.group(1).lower()
        n = int(word) if word.isdigit() else _COUNT[word]
        if 0 < n < len(everything):
            return everything[:n]
    if _EXPLOITED.search(title or ""):
        # "CISA has added CVE-A and CVE-B to its KEV catalog": the IDs in sentences about
        # exploitation that name a few, not the "CVE-A through CVE-H" bulletin line.
        tied: list[str] = []
        for text in (lead, *rest):
            for sentence in _SENTENCE.split(text or ""):
                ids = extract_cves(sentence)
                if ids and len(ids) <= SMALL_LIST and _EXPLOITED.search(sentence):
                    tied += [c for c in ids if c not in tied]
        if tied and len(tied) < len(everything):
            return tied
    text = " ".join(t or "" for t in (lead, *rest)).upper()
    repeated = [c for c in everything if text.count(c) > 1]
    return repeated or everything[:1]


# Coverage that says there is no fix. Checked on titles and lead paragraphs only: bodies often
# mention "unpatched systems" in passing.
UNPATCHED = re.compile(
    r"\b(?:unpatched|no (?:patch|fix)(?:es)?(?: is| are)? (?:yet )?(?:available|released)"
    r"|without (?:a )?(?:patch|fix)|not yet (?:patched|fixed)|yet to (?:be )?(?:patch|fix)(?:ed)?)\b",
    re.IGNORECASE,
)


def says_unpatched(*texts: str) -> bool:
    return any(UNPATCHED.search(t or "") for t in texts)


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
    # "extortion" alone is not ransomware (sextortion, extortion rings, ...).
    (Category.ransomware, _keywords(r"ransomware", r"LockBit", r"Akira", r"Cl0p", r"Black Basta")),
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
