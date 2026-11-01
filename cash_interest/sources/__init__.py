"""One parser per place Trading 212 publishes its cash rates, behind one interface:

    await source.fetch() -> list[Rate(ccy, apy, source, region, fetched_at)]

or a FetchError saying why not (Blocked, Unavailable, ParseError).
"""

from collections.abc import Callable
from datetime import datetime

import httpx

from cash_interest.sources.base import (
    Blocked,
    FetchError,
    ParseError,
    Rate,
    Region,
    Source,
    SourceId,
    Unavailable,
    http_client,
    utcnow,
)
from cash_interest.sources.stores import AppStore, GooglePlay
from cash_interest.sources.website import Cards, InterestOnCash

# The order rates are trusted in, and shown in: the rate page first, the store listings last.
ORDER = (SourceId.SITE, SourceId.CARDS, SourceId.APP_STORE, SourceId.GOOGLE_PLAY)
SOURCES: dict[SourceId, type[Source]] = {
    SourceId.SITE: InterestOnCash,
    SourceId.CARDS: Cards,
    SourceId.APP_STORE: AppStore,
    SourceId.GOOGLE_PLAY: GooglePlay,
}


def all_sources(client: httpx.AsyncClient, region: Region, clock: Callable[[], datetime] = utcnow) -> list[Source]:
    return [SOURCES[source_id](client, region, clock) for source_id in ORDER]


__all__ = [
    "ORDER",
    "SOURCES",
    "Blocked",
    "FetchError",
    "ParseError",
    "Rate",
    "Region",
    "Source",
    "SourceId",
    "Unavailable",
    "all_sources",
    "http_client",
    "utcnow",
]
