"""Writes the bot's real replies to docs/media/src/shots.json for the README screenshots.

    uv run python scripts/export_shots.py && (cd docs/media && npm install && node render.mjs)

Each shot is produced by the same functions the handlers call — parsing, the calculation, the
chart, the replies and the buttons — against a store seeded from the saved pages in
tests/fixtures, so the screenshots cannot drift from what the bot actually says. Only the clock is
fixed, to keep the output reproducible.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from aiogram.types import InlineKeyboardMarkup

from cash_interest.bot import replies
from cash_interest.bot.handlers import Reply, Services, build_reply, input_error, known_currencies
from cash_interest.bot.parsing import InputError, parse_query
from cash_interest.sources import Rate, Region, SourceId
from cash_interest.sources.stores import AppStore, GooglePlay
from cash_interest.sources.website import page_rates
from cash_interest.store import Status, Store

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
MEDIA = ROOT / "docs" / "media"
OUT = MEDIA / "src" / "shots.json"
# Charts go where the renderer serves static files from (staticFile in shots.tsx).
PUBLIC = MEDIA / "public"
# The evening the saved pages were captured, when the website and the stores disagreed.
NOW = datetime(2026, 11, 1, 20, 30, tzinfo=UTC)
REGION = Region.EU

Shot = list[dict[str, Any]]


def _keys(markup: InlineKeyboardMarkup | None) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard] if markup else []


async def _seeded() -> Services:
    """A fresh store holding what the four sources said on 1 November 2026.

    The website pages arrive as the owner's saved pages (that is how they reach the bot: the
    site answers non-browsers with a bot check); the store listings as live reads.
    """
    store = await Store.open(":memory:")
    for source, name in [(SourceId.SITE, "interest-on-cash.html"), (SourceId.CARDS, "cards.html")]:
        page = (FIXTURES / "website" / name).read_text(encoding="utf-8")
        await store.record(source, REGION, page_rates(page, source, REGION, NOW), at=NOW, via="upload")
    async with httpx.AsyncClient() as client:
        apple = AppStore(client, REGION).parse((FIXTURES / "stores" / "app-store-cy.json").read_bytes(), NOW)
        google = GooglePlay(client, REGION).parse((FIXTURES / "stores" / "google-play-cy.html").read_bytes(), NOW)
    await store.record(SourceId.APP_STORE, REGION, apple, at=NOW)
    await store.record(SourceId.GOOGLE_PLAY, REGION, google, at=NOW)
    return Services(store, REGION, clock=lambda: NOW)


def _args(command: str) -> str:
    """What aiogram hands a command handler: the text after `/rate`."""
    return command.partition(" ")[2]


def _photo_reply(reply: Reply, photo: str, public: Path) -> dict[str, Any]:
    if reply.chart is None:
        raise RuntimeError(f"{photo}: the chart did not render")
    (public / photo).write_bytes(reply.chart)
    return {"html": reply.caption, "keyboard": _keys(reply.keyboard), "photo": photo}


async def _rate(services: Services, text: str, photo: str, public: Path, prefer: SourceId | None = None) -> Shot:
    query = parse_query(_args(text), await known_currencies(services))
    reply = await build_reply(services, query, prefer)
    return [{"out": text}, {"in": _photo_reply(reply, photo, public)}]


async def _error(services: Services, text: str) -> Shot:
    try:
        parse_query(_args(text), await known_currencies(services))
    except InputError as error:
        return [{"out": text}, {"in": {"html": input_error(error), "keyboard": []}}]
    raise RuntimeError(f"{text!r} was supposed to be an error")


async def _current(store: Store, source: SourceId) -> list[Rate]:
    state = await store.state(source, REGION)
    if state.ok_at is None:
        raise RuntimeError(f"{source} was not seeded")
    return [
        Rate(ccy=ccy, apy=apy, source=source, region=REGION, fetched_at=state.ok_at) for ccy, apy in state.rates.items()
    ]


async def _rates_stale(services: Services) -> Shot:
    """The website as it is most days: its last saved page on show, live checks refused."""
    store, later = services.store, NOW + timedelta(hours=6)
    for source in (SourceId.SITE, SourceId.CARDS):
        await store.record_failure(source, REGION, Status.BLOCKED, "HTTP 403, bot check", at=later)
    # The same poll reads the store listings, which answer as usual and have not changed.
    for source in (SourceId.APP_STORE, SourceId.GOOGLE_PLAY):
        same = [rate.model_copy(update={"fetched_at": later}) for rate in await _current(store, source)]
        await store.record(source, REGION, same, at=later)
    states = await store.states(REGION)
    return [{"out": "/rates"}, {"in": {"html": replies.rates_table(states, REGION), "keyboard": []}}]


async def build(public: Path) -> dict[str, Shot]:
    """Every shot; the charts go into `public`, which must exist."""
    shots: dict[str, Shot] = {}
    services = await _seeded()
    shots["rate"] = await _rate(services, "/rate EUR 20000 5y", "rate.png", public)
    # The demo taps the App Store button on the reply above; this is what the bot edits it into.
    shots["rate_app"] = await _rate(services, "/rate EUR 20000 5y", "rate_app.png", public, SourceId.APP_STORE)
    shots["small"] = await _rate(services, "/rate USD 10 30d", "small.png", public)
    shots["diff"] = [{"out": "/diff"}, {"in": {"html": replies.diff(await services.store.states(REGION), REGION),
                                               "keyboard": []}}]  # fmt: skip
    shots["errors"] = [
        line
        for text in ("/rate eru 20000", "/rate eur 20k banana", "/rate eur 20000 11y")
        for line in await _error(services, text)
    ]
    await services.store.close()
    # The table changes the store, so it starts from its own copy of the seed.
    services = await _seeded()
    shots["rates"] = await _rates_stale(services)
    await services.store.close()
    return shots


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    shots = asyncio.run(build(PUBLIC))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(shots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {', '.join(shots)}")


if __name__ == "__main__":
    main()
