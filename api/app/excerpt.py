"""The feed's own excerpt, shown in the expanded row when a row has no summary.

The outlet's RSS excerpt, cleaned (markup, "The post ... appeared first on ...", "Read more",
a leading copy of the title) and cut to its first one or two sentences, at most MAX_CHARS.
Too short to say anything (under MIN_CHARS) is no excerpt: the row then has nothing to expand.
"""

import html
import re

from app.models import Item

MAX_CHARS = 220
MIN_CHARS = 40

_TAGS = re.compile(r"<[^>]+>")
_TAIL = re.compile(
    r"\s*(The post .{0,300}? appeared first on .*|(Continue|Keep) reading.*|Read (the )?(more|full).*|\[(…|\.\.\.)\]\s*)$",
    re.I | re.S,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])")


def _clean(text: str, title: str) -> str:
    text = " ".join(html.unescape(_TAGS.sub(" ", text)).split())
    text = _TAIL.sub("", text).strip()
    for head in (title, title.rstrip(".")):
        if head and text.lower().startswith(head.lower()):
            text = text[len(head) :].lstrip(" .:-–—")
    return text


def _cut(text: str) -> str:
    sentences = [s for s in _SENTENCE.split(text) if s]
    if not sentences:
        return ""
    out = sentences[0]
    if len(sentences) > 1 and len(out) + 1 + len(sentences[1]) <= MAX_CHARS:
        out = f"{out} {sentences[1]}"
    if len(out) > MAX_CHARS:
        out = out[: MAX_CHARS - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return out


def row_excerpt(item: Item) -> dict | None:
    """{"source": outlet name, "text": first sentences} from the primary article's excerpt,
    else the first article with a usable one; None when there is none."""
    sources = sorted(item.sources, key=lambda s: s.url != item.primary_url)
    for s in sources:
        if not s.excerpt:
            continue
        text = _cut(_clean(s.excerpt, s.title or item.headline))
        if len(text) >= MIN_CHARS and text.lower() != item.headline.lower():
            return {"source": s.source.name, "text": text}
    return None


def expandable(item: Item, excerpt: dict | None) -> bool:
    """A CVE row always expands; a plain row only when it has a summary or an excerpt."""
    return bool(item.cve_id or item.summary or excerpt)
