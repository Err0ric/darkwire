"""Version ranges in article facts and summaries: is a stated fix inside the stated affected range?

"Affected: RouterOS <7.24" with "Fixed: 7.23 or later" cannot both be right (7.23 is affected).
conflict() finds that for the facts (app/facts.py drops both, unless the quote names separate
release branches), summary_conflict() for a summary's own text (app/summaries.py regenerates it
without version numbers, then strips them).

A fixed version is compared with the affected bound of its own line when the range names several
(Roundcube "1.6.x before 1.6.16 and 1.7.x before 1.7.1" with fixes 1.6.16 and 1.7.1 is fine), and
with the single bound otherwise.
"""

import re

V = r"(\d+(?:\.\d+)+)"
_LT = re.compile(rf"(?:<(?!=)|\bbefore\b|\bbelow\b|\bprior to\b|\bearlier than\b|\bolder than\b|\blower than\b)\s*(?:v(?:ersion)?\s*)?{V}", re.I)
_LE = re.compile(rf"(?:<=|\bup to\b|\bthrough\b|\bthru\b)\s*(?:v(?:ersion)?\s*)?{V}|{V}\s*(?:and|or)\s*(?:prior|earlier|older|below|lower)\b", re.I)
_FIX_IN_TEXT = re.compile(
    rf"\b(?:fixed|patched|addressed|resolved|remediated|corrected)\s+in\s+(?:\w+\s+)?(?:v(?:ersion)?\s*)?{V}"
    rf"|\b(?:update|upgrade|updating|upgrading|move|moving)\s+(?:\w+\s+)?to\s+(?:v(?:ersion)?\s*)?{V}"
    rf"|{V}\s+(?:or|and)\s+(?:later|newer|above)\b"
    rf"|\bversion\s+{V}\s+(?:fixes|addresses|resolves|patches)\b",
    re.I,
)
BRANCH = re.compile(r"\b(stable|long[- ]term|LTS|branch(?:es)?|channels?|mainline|release train|extended support|ESR)\b", re.I)


def parse(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def bounds(text: str) -> list[tuple[str, tuple[int, ...]]]:
    """[("<" or "<=", version)] the text states for affected versions."""
    out = [("<", parse(m.group(1))) for m in _LT.finditer(text or "")]
    for m in _LE.finditer(text or ""):
        out.append(("<=", parse(m.group(1) or m.group(2))))
    return out


def versions(text: str) -> list[tuple[int, ...]]:
    return [parse(v) for v in re.findall(V, text or "")]


def _inside(fixed: tuple[int, ...], stated: list[tuple[str, tuple[int, ...]]]) -> bool:
    lines = {b[:2] for _, b in stated}
    for op, b in stated:
        # Several ranges: compare a fix only with the bound of its own major.minor line.
        if len(lines) > 1 and b[:2] != fixed[:2]:
            continue
        if (op == "<" and fixed < b) or (op == "<=" and fixed <= b):
            return True
    return False


def conflict(affected: str, fixed: str) -> bool:
    """A fixed version inside the affected range."""
    stated = bounds(affected)
    return bool(stated) and any(_inside(f, stated) for f in versions(fixed))


def summary_fixes(text: str) -> list[tuple[int, ...]]:
    return [parse(next(g for g in m.groups() if g)) for m in _FIX_IN_TEXT.finditer(text or "")]


def summary_conflict(text: str) -> bool:
    """The summary states a fix version inside its own affected range."""
    stated = bounds(text)
    return bool(stated) and any(_inside(f, stated) for f in summary_fixes(text))


def branches(fixed: str, quote: str) -> list[dict]:
    """[{"version", "branch"}] when a fixed value names one version per release branch
    ("7.24 stable, 7.23.5 long-term"); the branch word comes from the value, else the quote."""
    out = []
    for part in re.split(r",|;|\band\b", fixed or ""):
        found = re.search(V, part)
        if not found:
            continue
        label = BRANCH.search(part) or _near(found.group(1), quote)
        out.append({"version": found.group(1), "branch": label.group(0) if label else ""})
    return out if len(out) >= 2 and all(b["branch"] for b in out) else []


def _near(version: str, quote: str):
    """The branch word right before or after a version in the quote."""
    i = (quote or "").find(version)
    if i < 0:
        return None
    return BRANCH.search(quote[i + len(version): i + len(version) + 30]) or BRANCH.search(quote[max(0, i - 30): i])


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def strip(text: str) -> str:
    """The summary without the sentences that state an affected range or a fix version (whole
    sentences, so what is left still reads); empty when nothing else is left."""
    kept = [s for s in _SENTENCE.split(text or "") if s.strip() and not bounds(s) and not summary_fixes(s)]
    return " ".join(kept).strip()
