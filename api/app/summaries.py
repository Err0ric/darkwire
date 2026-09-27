"""Three-line row summaries, generated once per item with Claude and cached in items.summary.

Runs at the end of each enrichment pass so CVE rows are summarized with their NVD facts
(affected versions, fix status). Never regenerated. Without ANTHROPIC_API_KEY it does nothing
and the expanded row simply has no summary. actions_pending() reads fixed versions and
workarounds out of the articles for the "What to do" block, same model, same rules.

Every pass records the model's health in job_state ("summaries_health"): ok, auth_failing,
quota, error, or no_key. /status reports it and the rail says "summaries paused" when not ok.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import anthropic
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import jobstate
from app.config import get_settings
from app.models import Cve, Item, ItemCve, ItemSource, PatchStatus, Stream

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
PER_RUN = 40
CONCURRENCY = 4
# A CVE row waits this long for NVD before being summarized from the articles alone.
NVD_GRACE = timedelta(hours=2)
HEALTH = "summaries_health"

SYSTEM = """You write the summary under a headline on darkwire, a board of security news and CVEs read by security engineers.

Write at most three short sentences, under 60 words in total, covering in order:
1. What it is: the flaw, incident or finding, in concrete terms.
2. Who is affected: products and versions, organizations, or users.
3. Whether there is a fix: patched versions, a workaround, or no fix yet.

Use only facts from the material provided. If the material does not say whether a fix exists, leave the third point out entirely; never write that something is unknown or not stated. Do not speculate.
No adjectives of emphasis (critical, severe, major, alarming), no marketing language, no advice, no headline restatement, no source names.
Plain text only: no markdown, no bullet points, no preamble."""

PATCH_TEXT = {
    PatchStatus.patched: "a fix is available",
    PatchStatus.no_fix: "no fix is available",
    PatchStatus.workaround: "no fix; a workaround is available",
    PatchStatus.unverified: "fix status not verified",
}


def _material(item: Item, cve: Cve | None) -> str:
    lines = [f"Headline: {item.headline}"]
    for s in item.sources:
        if s.excerpt:
            lines.append(f"Article excerpt: {s.excerpt}")
    if cve is not None and cve.fetched_at is not None:
        if cve.description:
            lines.append(f"{cve.id} (NVD): {cve.description}")
        if cve.affected:
            lines.append(f"Affected versions: {cve.affected}")
        if cve.patch_status:
            lines.append(f"Fix status: {PATCH_TEXT[cve.patch_status]}")
    return "\n".join(lines)


ACTION_SYSTEM = """You read security articles about a vulnerability and extract what a defender can do about it.

Return one JSON object and nothing else:
{"fixed": ["<product> <first fixed version or update/KB ID>", ...], "workaround": "<one sentence>" or null}

Rules:
- Only facts stated in the material. Never infer a version, never guess.
- "fixed": at most 4 entries, product name then the version, build or KB that fixes it. Empty list if none is stated.
- "workaround": one plain imperative sentence under 25 words (e.g. "Disable the WebDAV service on exposed hosts.") only if the material names a concrete mitigation other than patching. Otherwise null.
- No adjectives of emphasis, no markdown, no commentary."""

BODY_CHARS = 4000


def _action_material(item: Item, cve: Cve | None) -> str:
    lines = [f"Headline: {item.headline}"]
    if cve is not None:
        if cve.description:
            lines.append(f"{cve.id} (NVD): {cve.description}")
        if cve.affected:
            lines.append(f"Affected versions: {cve.affected}")
    for s in item.sources:
        text = (s.body or s.excerpt or "")[:BODY_CHARS]
        if text:
            lines.append("Article:\n" + text)
    return "\n\n".join(lines)


def _parse_action(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        raw = json.loads(text[start : end + 1])
    except ValueError:
        return None
    fixed = [f.strip() for f in raw.get("fixed") or [] if isinstance(f, str) and f.strip()][:4]
    workaround = raw.get("workaround")
    workaround = workaround.strip() if isinstance(workaround, str) and workaround.strip() else None
    return {"fixed": fixed, "workaround": workaround}


def _ready(item: Item, cve: Cve | None, now: datetime) -> bool:
    # Rows without a CVE are ready at once; CVE rows once NVD answered or after a grace period.
    return cve is None or cve.fetched_at is not None or now - item.first_seen_at > NVD_GRACE


# ---------------------------------------------------------------- health


def _classify(e: anthropic.APIError) -> str:
    """Map an API failure onto the health states /status reports."""
    if isinstance(e, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return "auth_failing"
    if isinstance(e, anthropic.RateLimitError):
        return "quota"
    message = str(getattr(e, "message", e)).lower()
    if isinstance(e, anthropic.BadRequestError) and ("credit" in message or "billing" in message):
        return "quota"
    return "error"


async def record_health(session: AsyncSession, state: str, detail: str | None = None) -> None:
    await jobstate.put(
        session, HEALTH, json.dumps({"state": state, "at": datetime.now(UTC).isoformat(), "detail": detail})
    )
    await session.commit()


async def health(session: AsyncSession) -> dict:
    """{"state", "at", "detail"}. no_key is read live; "pending" means a key but no pass yet."""
    if not get_settings().anthropic_api_key:
        return {"state": "no_key", "at": None, "detail": None}
    raw = await jobstate.get(session, HEALTH)
    if not raw:
        return {"state": "pending", "at": None, "detail": None}
    data = json.loads(raw)
    return {"state": data.get("state", "error"), "at": data.get("at"), "detail": data.get("detail")}


# ---------------------------------------------------------------- calls


async def _run(
    session: AsyncSession,
    items: list[Item],
    call: Callable[[anthropic.AsyncAnthropic, Item], Awaitable[anthropic.types.Message]],
    parse: Callable[[anthropic.types.Message], object | None],
    label: str,
) -> list[object | None]:
    """Call the model once per item, CONCURRENCY at a time. The first auth, quota or connection
    failure stops the pass (the rest wait for the next one) and is recorded as the health state."""
    key = get_settings().anthropic_api_key
    sem = asyncio.Semaphore(CONCURRENCY)
    stop = asyncio.Event()
    failure: list[tuple[str, str]] = []
    successes = 0

    async with anthropic.AsyncAnthropic(api_key=key, max_retries=3) as client:

        async def one(item: Item) -> object | None:
            nonlocal successes
            if stop.is_set():
                return None
            async with sem:
                if stop.is_set():
                    return None
                try:
                    msg = await call(client, item)
                except anthropic.APIConnectionError as e:
                    log.warning("%s: connection error, stopping: %s", label, e)
                    failure.append(("error", f"connection: {e}"))
                    stop.set()
                    return None
                except anthropic.APIStatusError as e:
                    state = _classify(e)
                    if state == "error":
                        log.warning("%s: item %d failed: HTTP %d", label, item.id, e.status_code)
                        failure.append(("error", f"HTTP {e.status_code}"))
                        return None
                    log.warning("%s: %s, stopping (%s)", label, state, e.message)
                    failure.append((state, e.message[:200]))
                    stop.set()
                    return None
            successes += 1
            return parse(msg)

        results = await asyncio.gather(*(one(i) for i in items))

    # Auth and quota outrank a one-off error; any success with no hard failure is ok.
    hard = next((f for f in failure if f[0] in ("auth_failing", "quota")), None)
    if hard:
        await record_health(session, *hard)
    elif successes:
        await record_health(session, "ok")
    elif failure:
        await record_health(session, *failure[0])
    return results


def _text(msg: anthropic.types.Message) -> str | None:
    if msg.stop_reason not in ("end_turn", "max_tokens"):
        return None
    text = " ".join(b.text for b in msg.content if b.type == "text").strip()
    return text or None


async def summarize_pending(session: AsyncSession) -> int | None:
    """Summarize up to PER_RUN items that have none. None when skipped (no key)."""
    if not get_settings().anthropic_api_key:
        return None
    now = datetime.now(UTC)
    items = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, or_(Item.summary.is_(None), Item.summary == ""))
            .options(selectinload(Item.sources).selectinload(ItemSource.source), selectinload(Item.cve))
            .order_by(Item.last_event_at.desc())
            .limit(PER_RUN * 3)
        )
    ).all()
    todo = [i for i in items if _ready(i, i.cve, now)][:PER_RUN]
    if not todo:
        return 0

    results = await _run(
        session,
        todo,
        lambda client, item: client.messages.create(
            model=MODEL, max_tokens=300, system=SYSTEM,
            messages=[{"role": "user", "content": _material(item, item.cve)}],
        ),
        _text,
        "summaries",
    )
    written = 0
    for item, text in zip(todo, results, strict=True):
        if text:
            item.summary = text
            written += 1
    await session.commit()
    return written


async def actions_pending(session: AsyncSession) -> int | None:
    """Read fixed versions and workarounds out of the articles for CVE rows, once each.
    None when skipped (no key). Stored even when empty so an item is asked only once."""
    if not get_settings().anthropic_api_key:
        return None
    now = datetime.now(UTC)
    items = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.action.is_(None), Item.id.in_(select(ItemCve.item_id)))
            .options(selectinload(Item.sources), selectinload(Item.cve))
            .order_by(Item.last_event_at.desc())
            .limit(PER_RUN * 3)
        )
    ).all()
    todo = [i for i in items if i.sources and _ready(i, i.cve, now)][:PER_RUN]
    if not todo:
        return 0

    def parse(msg: anthropic.types.Message) -> dict | None:
        if msg.stop_reason != "end_turn":
            return None
        return _parse_action(" ".join(b.text for b in msg.content if b.type == "text"))

    results = await _run(
        session,
        todo,
        lambda client, item: client.messages.create(
            model=MODEL, max_tokens=400, system=ACTION_SYSTEM,
            messages=[{"role": "user", "content": _action_material(item, item.cve)}],
        ),
        parse,
        "actions",
    )
    written = 0
    for item, action in zip(todo, results, strict=True):
        if action is not None:
            item.action = action
            written += 1
    await session.commit()
    return written
