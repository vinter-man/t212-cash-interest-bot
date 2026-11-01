"""Shared fixtures: the saved pages, a fixed clock, and an in-memory store."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from cash_interest.board import SourceState
from cash_interest.sources import Rate, Region, SourceId
from cash_interest.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
# When the fixtures were saved: 1 November 2026, the day the website and the stores disagreed.
NOW = datetime(2026, 11, 1, 20, 30, tzinfo=UTC)
TODAY = date(2026, 11, 2)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def rates(source: SourceId, values: Mapping[str, str], region: Region = Region.EU, at: datetime = NOW) -> list[Rate]:
    return [Rate(ccy=ccy, apy=Decimal(apy), source=source, region=region, fetched_at=at) for ccy, apy in values.items()]


def state(
    source: SourceId,
    values: Mapping[str, str],
    *,
    at: datetime = NOW,
    failing_since: datetime | None = None,
    problem: str | None = None,
    via: str = "http",
) -> SourceState:
    return SourceState(
        source=source,
        rates={ccy: Decimal(apy) for ccy, apy in values.items()},
        ok_at=at if values else None,
        via=via if values else None,
        checked_at=failing_since or at,
        failing_since=failing_since,
        problem=problem,
    )


# What the four sources said on 1 November 2026 for the EU view (see tests/fixtures).
SITE_EU = {"EUR": "0.025", "GBP": "0.0355", "USD": "0.034", "PLN": "0.0225", "CZK": "0.03"}
STORE_EU = {"EUR": "0.022", "GBP": "0.038", "USD": "0.033"}


@pytest.fixture
def states() -> dict[SourceId, SourceState]:
    return {
        SourceId.SITE: state(SourceId.SITE, SITE_EU),
        SourceId.CARDS: state(SourceId.CARDS, SITE_EU),
        SourceId.APP_STORE: state(SourceId.APP_STORE, STORE_EU),
        SourceId.GOOGLE_PLAY: state(SourceId.GOOGLE_PLAY, STORE_EU),
    }


@pytest.fixture
async def store() -> AsyncIterator[Store]:
    async with await Store.open(":memory:") as opened:
        yield opened
