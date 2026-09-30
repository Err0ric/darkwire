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


# Emoji and their joiners: pictographs, flags, skin tones and tag sequences (U+1F000-1FAFF,
# U+E0020-E007F), the symbol and dingbat blocks (U+2600-27BF), the few emoji in other blocks, and
# the variation selector and zero-width joiner that bind them. Letters, punctuation, arrows, and
# signs like the trade mark stay.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U000E0020-\U000E007F☀-➿⌚⌛⏩-⏳⏸-⏺"
    "⭐⭕⬛⬜️‍⃣]"
)


def strip_emoji(text: str) -> str:
    """The text without emoji, spaces collapsed ("🧮 Hey Siri, ..." -> "Hey Siri, ...")."""
    return _WS_RE.sub(" ", _EMOJI.sub("", text or "")).strip()


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


def headline_count(title: str | None) -> int | None:
    """"Two ... Zero-Days" -> 2, "2 exploited zero-days" -> 2; None when the title counts nothing."""
    counted = _COUNTED.search(title or "")
    if not counted:
        return None
    word = counted.group(1).lower()
    n = int(word) if word.isdigit() else _COUNT[word]
    return n if n > 0 else None


def cluster_cves(articles: list[tuple[str, str, str]]) -> list[str]:
    """headline_cves for a whole cluster of (title, lead, body) articles. Each article's IDs
    count; when a title counts the issues ("Two ... Zero-Days") and the articles tie fewer than
    that, the first IDs the cluster's texts name fill up to the count (one outlet counts, another
    lists the bulletin)."""
    tied: list[str] = []
    for title, lead, body in articles:
        tied += [c for c in headline_cves(title, lead or "", body or "") if c not in tied]
    n = max((headline_count(t) or 0 for t, _, _ in articles), default=0)
    if len(tied) < n:
        named = extract_cves(*(t for _, lead, body in articles for t in (lead or "", body or "")))
        tied += [c for c in named if c not in tied][: n - len(tied)]
    return tied


LEDE_PARAGRAPHS = 2


def _plain_line(line: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (line or "").lower())


def subject_cves(title: str, lead: str, text: str) -> set[str]:
    """The CVEs an article is about, not ones it mentions for context: IDs in the title, in the
    lede (the feed excerpt and the first LEDE_PARAGRAPHS paragraphs of the text), or named at
    least twice in the text. Extracted article text often starts with the headline itself; that
    line is not a lede paragraph."""
    heading = _plain_line(title)
    paragraphs = [p for p in (text or "").splitlines() if p.strip() and _plain_line(p) != heading][:LEDE_PARAGRAPHS]
    found = set(extract_cves(title or "", lead or "", *paragraphs))
    upper = (text or "").upper()
    return found | {c for c in extract_cves(text or "") if upper.count(c) >= 2}


def subject_reasons(title: str, lead: str, text: str) -> dict[str, str]:
    """For each subject CVE (subject_cves), the sentence that qualifies it: the title, the lede
    sentence naming it, or (named twice) its first sentence in the text. For the logs."""
    subjects = subject_cves(title, lead, text)
    out: dict[str, str] = {}
    heading = _plain_line(title)
    paragraphs = [p for p in (text or "").splitlines() if p.strip() and _plain_line(p) != heading][:LEDE_PARAGRAPHS]
    places = [title or "", *_SENTENCE.split(lead or ""), *(s for p in paragraphs for s in _SENTENCE.split(p)),
              *_SENTENCE.split(" ".join((text or "").split()))]
    for cve in subjects:
        out[cve] = next((s for s in places if cve in s.upper()), "")
    return out


def row_subject_cves(sources) -> set[str]:
    """subject_cves over a row's stored articles (anything with .title, .excerpt, .body)."""
    out: set[str] = set()
    for s in sources:
        out |= subject_cves(s.title or "", s.excerpt or "", s.body or "")
    return out


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
    n = headline_count(title)
    if n and n < len(everything):
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


# Explainers, trend pieces and webinars are not incidents: Research when they are about attacks or
# threats, else News ("Know Your Enemy: Browser-Based Attack Techniques in 2026").
EXPLAINER = _keywords(
    r"know your enemy", r"techniques", r"how to", r"guide", r"explained", r"explainer", r"what is", r"webinar",
    r"best practices", r"trends", r"lessons learned", r"checklist", r"tips", r"primer", r"playbook", r"deep dive",
    r"year in review", r"predictions",
)
# Trend and industry pieces ("Google: AI Is Changing the Pace and Profile of Vulnerability
# Discovery", 2026-09-30): about vulnerabilities in general, no specific flaw, product or CVE.
TREND = _words(
    r"(?:is|are) changing", r"changing the", r"(?:the )?pace of", r"profile of", r"landscape", r"state of",
    r"future of", r"rise of", r"era of", r"age of", r"industry", r"surveys?", r"report finds", r"study finds",
    r"statistics", r"by the numbers", r"vulnerability (?:discovery|management|research|disclosure|programs?)",
    r"bug bount(?:y|ies)",
)
_ABOUT_FLAWS = _keywords(r"vulnerability", r"vulnerabilities", r"flaw", r"zero-days?", r"exploits?", r"CVEs?")
_ABOUT_THREATS = _keywords(r"attacks?", r"threats?", r"malware", r"phishing", r"ransomware", r"hackers?", r"exploits?", r"campaigns?")
# A breach is an incident: something stolen, exposed or intruded upon. Needed when "breach" only
# appears in the first paragraph (a trend piece mentions breaches in passing).
BREACH_INCIDENT = _keywords(
    r"stole", r"stolen", r"exposed", r"leaked", r"exfiltrated", r"compromised", r"breached", r"hacked",
    r"unauthorized access", r"intrusion", r"accessed", r"notified", r"impacted", r"heist", r"theft",
    r"without authorization",
)


def guess_category(title: str, excerpt: str, has_cve: bool, trends: bool = True) -> Category:
    """Title first. The first paragraph is only consulted when the title matches nothing. An
    explainer title is Research (about threats) or News, never Breach; a breach found only in the
    first paragraph needs an incident word there too. A trend or industry piece with no CVE is not
    a Vulnerability (that needs a specific flaw, product or CVE): Research when it is about flaws
    or threats, else News. `trends=False`: the rule before that (for the one-time re-derivation)."""
    if EXPLAINER.search(title or ""):
        return Category.research if _ABOUT_THREATS.search(title) else Category.news
    for text, lead in ((title, False), (excerpt, True)):
        for category, pattern in CATEGORY_RULES:
            if pattern.search(text or ""):
                if category == Category.breach and lead and not BREACH_INCIDENT.search(f"{title} {text}"):
                    continue
                if category == Category.vulnerability and trends and not has_cve and TREND.search(title or ""):
                    return Category.research if _ABOUT_THREATS.search(title) or _ABOUT_FLAWS.search(title) else Category.news
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
