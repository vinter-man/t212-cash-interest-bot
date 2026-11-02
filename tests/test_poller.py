"""A polling cycle: every outcome is recorded, and only a real change reaches subscribers."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest

from cash_interest.poller import poll, status_of
from cash_interest.sources import Blocked, FetchError, ParseError, Rate, Region, Source, SourceId, Unavailable
from cash_interest.store import Change, Status, Store
from tests.conftest import NOW, rates


class Fake(Source):
    """A source that answers from a script: rates, or an exception, one per poll."""

    def __init__(self, source: SourceId, answers: list[dict[str, str] | Exception]) -> None:
        super().__init__(httpx.AsyncClient(), Region.EU, lambda: NOW)
        self.id = source  # type: ignore[misc]
        self.answers = answers

    def url(self) -> str:
        return "https://example.test"

    def parse(self, body: bytes, fetched_at: datetime) -> list[Rate]:
        raise NotImplementedError

    async def fetch(self) -> list[Rate]:
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return rates(self.id, answer, at=self.clock())


class Recorder:
    def __init__(self) -> None:
        self.calls: list[list[Change]] = []

    async def __call__(self, changes: Sequence[Change]) -> None:
        self.calls.append(list(changes))


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (Blocked("HTTP 403, bot check"), Status.BLOCKED),
        (Unavailable("HTTP 502"), Status.UNAVAILABLE),
        (ParseError("no rates"), Status.PARSE_ERROR),
        (FetchError("other"), Status.ERROR),
    ],
)
def test_status_of(error: FetchError, status: Status) -> None:
    assert status_of(error) is status


async def test_every_outcome_is_recorded(store: Store) -> None:
    sources = [
        Fake(SourceId.SITE, [Blocked("HTTP 403, bot check")]),
        Fake(SourceId.CARDS, [ParseError("no interestOnCashRates on the page")]),
        Fake(SourceId.APP_STORE, [{"EUR": "0.022"}]),
        Fake(SourceId.GOOGLE_PLAY, [RuntimeError("a parser bug")]),
    ]
    report = await poll(store, sources, lambda: NOW)
    assert report.found == {SourceId.APP_STORE: 1}
    assert report.failed == {
        SourceId.SITE: "HTTP 403, bot check",
        SourceId.CARDS: "no interestOnCashRates on the page",
        SourceId.GOOGLE_PLAY: "unexpected RuntimeError",
    }
    states = await store.states(Region.EU)
    assert states[SourceId.SITE].problem == "HTTP 403, bot check"
    assert states[SourceId.GOOGLE_PLAY].problem == "RuntimeError"
    assert states[SourceId.APP_STORE].rates == {"EUR": Decimal("0.022")}
    assert "app_store: 1 rates" in report.summary()


async def test_no_false_alerts(store: Store) -> None:
    """A value, a failure, the same value, a parse error, then a real change: one alert."""
    source = Fake(
        SourceId.APP_STORE,
        [{"EUR": "0.022"}, Unavailable("HTTP 502"), {"EUR": "0.022"}, ParseError("reworded"), {"EUR": "0.023"}],
    )
    notify = Recorder()
    for hours in range(5):
        await poll(store, [source], lambda h=hours: NOW + timedelta(hours=6 * h), notify)  # type: ignore[misc]
    assert len(notify.calls) == 1
    (change,) = notify.calls[0]
    assert (change.ccy, change.old, change.new) == ("EUR", Decimal("0.022"), Decimal("0.023"))


async def test_a_stale_value_stays_on_show(store: Store) -> None:
    source = Fake(SourceId.SITE, [{"EUR": "0.025"}, Blocked("HTTP 403, bot check")])
    await poll(store, [source], lambda: NOW)
    await poll(store, [source], lambda: NOW + timedelta(hours=6))
    state = await store.state(SourceId.SITE, Region.EU)
    assert state.stale
    assert state.rates == {"EUR": Decimal("0.025")}


async def test_a_database_error_costs_one_source_not_the_poll(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    record = store.record

    async def flaky(source: SourceId, *args: Any, **kwargs: Any) -> list[Change]:
        if source is SourceId.APP_STORE:
            raise sqlite3.OperationalError("database is locked")
        return await record(source, *args, **kwargs)

    monkeypatch.setattr(store, "record", flaky)
    sources = [Fake(SourceId.APP_STORE, [{"EUR": "0.022"}]), Fake(SourceId.GOOGLE_PLAY, [{"EUR": "0.022"}])]
    report = await poll(store, sources, lambda: NOW)
    assert report.failed == {SourceId.APP_STORE: "not recorded"}
    assert report.found == {SourceId.GOOGLE_PLAY: 1}
    assert (await store.state(SourceId.GOOGLE_PLAY, Region.EU)).rates == {"EUR": Decimal("0.022")}


async def test_changes_from_several_sources_arrive_together(store: Store) -> None:
    app = Fake(SourceId.APP_STORE, [{"EUR": "0.022"}, {"EUR": "0.025"}])
    play = Fake(SourceId.GOOGLE_PLAY, [{"EUR": "0.022"}, {"EUR": "0.025"}])
    notify = Recorder()
    await poll(store, [app, play], lambda: NOW, notify)
    await poll(store, [app, play], lambda: NOW, notify)
    assert [[c.source for c in call] for call in notify.calls] == [[SourceId.APP_STORE, SourceId.GOOGLE_PLAY]]
