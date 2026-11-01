"""The store: what counts as a change, what makes a source stale, and subscriptions."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from cash_interest.sources import Region, SourceId
from cash_interest.store import Status, Store
from tests.conftest import NOW, rates

APP = SourceId.APP_STORE
LATER = NOW + timedelta(hours=6)
LATEST = NOW + timedelta(hours=12)


async def test_the_first_check_is_not_a_change(store: Store) -> None:
    assert await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022"}), at=NOW) == []


async def test_a_new_value_is_a_change(store: Store) -> None:
    await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022", "GBP": "0.038"}), at=NOW)
    changes = await store.record(APP, Region.EU, rates(APP, {"EUR": "0.023", "GBP": "0.038"}, at=LATER), at=LATER)
    assert [(c.ccy, c.old, c.new, c.at) for c in changes] == [("EUR", Decimal("0.022"), Decimal("0.023"), LATER)]


async def test_the_same_value_written_differently_is_not_a_change(store: Store) -> None:
    """ "3.30%" and "3.3%" are one rate."""
    await store.record(APP, Region.EU, rates(APP, {"USD": "0.0330"}), at=NOW)
    assert await store.record(APP, Region.EU, rates(APP, {"USD": "0.033"}), at=LATER) == []


async def test_currencies_that_appear_or_disappear_are_not_changes(store: Store) -> None:
    await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022", "USD": "0.033"}), at=NOW)
    assert await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022", "GBP": "0.038"}), at=LATER) == []
    state = await store.state(APP, Region.EU)
    assert set(state.rates) == {"EUR", "GBP"}


async def test_a_failure_between_two_checks_does_not_hide_a_change(store: Store) -> None:
    await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022"}), at=NOW)
    await store.record_failure(APP, Region.EU, Status.UNAVAILABLE, "HTTP 502", at=LATER)
    changes = await store.record(APP, Region.EU, rates(APP, {"EUR": "0.025"}), at=LATEST)
    assert [(c.old, c.new) for c in changes] == [(Decimal("0.022"), Decimal("0.025"))]


async def test_regions_and_sources_are_kept_apart(store: Store) -> None:
    await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022"}), at=NOW)
    await store.record(APP, Region.UK, rates(APP, {"EUR": "0.030"}, region=Region.UK), at=LATER)
    site = SourceId.SITE
    assert await store.record(site, Region.EU, rates(site, {"EUR": "0.025"}), at=LATER) == []
    assert (await store.state(APP, Region.EU)).rates == {"EUR": Decimal("0.022")}


async def test_rates_must_belong_to_the_source_they_are_recorded_for(store: Store) -> None:
    with pytest.raises(ValueError, match="another source"):
        await store.record(SourceId.SITE, Region.EU, rates(APP, {"EUR": "0.022"}), at=NOW)


async def test_a_failure_needs_a_failing_status(store: Store) -> None:
    with pytest.raises(ValueError, match="failing status"):
        await store.record_failure(APP, Region.EU, Status.OK, "", at=NOW)


class TestState:
    async def test_never_checked(self, store: Store) -> None:
        state = await store.state(APP, Region.EU)
        assert (state.rates, state.checked_at, state.stale) == ({}, None, False)

    async def test_healthy(self, store: Store) -> None:
        await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022"}), at=NOW)
        state = await store.state(APP, Region.EU)
        assert (state.ok_at, state.checked_at, state.failing_since, state.via) == (NOW, NOW, None, "http")
        assert not state.stale

    async def test_stale_since_the_first_failure(self, store: Store) -> None:
        await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022"}), at=NOW)
        await store.record_failure(APP, Region.EU, Status.BLOCKED, "HTTP 429, refused", at=LATER)
        await store.record_failure(APP, Region.EU, Status.UNAVAILABLE, "HTTP 502", at=LATEST)
        state = await store.state(APP, Region.EU)
        assert state.stale
        assert (state.failing_since, state.checked_at, state.problem) == (LATER, LATEST, "HTTP 502")
        assert state.rates == {"EUR": Decimal("0.022")}

    async def test_never_succeeded(self, store: Store) -> None:
        await store.record_failure(SourceId.SITE, Region.EU, Status.BLOCKED, "HTTP 403, bot check", at=NOW)
        state = await store.state(SourceId.SITE, Region.EU)
        assert (state.rates, state.failing_since, state.stale) == ({}, NOW, False)

    async def test_recovers(self, store: Store) -> None:
        await store.record_failure(APP, Region.EU, Status.BLOCKED, "HTTP 429", at=NOW)
        await store.record(APP, Region.EU, rates(APP, {"EUR": "0.022"}), at=LATER)
        state = await store.state(APP, Region.EU)
        assert (state.failing_since, state.problem, state.stale) == (None, None, False)

    async def test_an_uploaded_page_is_remembered_as_one(self, store: Store) -> None:
        site = SourceId.SITE
        await store.record(site, Region.EU, rates(site, {"EUR": "0.025"}), at=NOW, via="upload")
        await store.record_failure(site, Region.EU, Status.BLOCKED, "HTTP 403, bot check", at=LATER)
        state = await store.state(site, Region.EU)
        assert (state.via, state.stale) == ("upload", True)

    async def test_states_cover_every_source(self, store: Store) -> None:
        assert list(await store.states(Region.EU)) == list(SourceId)


async def test_last_check_counts_the_poller_not_uploads(store: Store) -> None:
    assert await store.last_check(Region.EU) is None
    await store.record_failure(APP, Region.EU, Status.BLOCKED, "HTTP 429", at=NOW)
    site = SourceId.SITE
    await store.record(site, Region.EU, rates(site, {"EUR": "0.025"}), at=LATER, via="upload")
    assert await store.last_check(Region.EU) == NOW
    assert await store.last_check(Region.UK) is None


async def test_subscriptions(store: Store) -> None:
    assert await store.subscribe(1, "EUR", at=NOW)
    assert not await store.subscribe(1, "EUR", at=NOW)
    assert await store.subscribe(1, "GBP", at=NOW)
    assert await store.subscribe(2, "EUR", at=NOW)
    assert await store.subscriptions(1) == ["EUR", "GBP"]
    assert await store.subscribers("EUR") == [1, 2]
    assert await store.unsubscribe(1, "EUR")
    assert not await store.unsubscribe(1, "EUR")
    assert await store.forget(2) == 1
    assert await store.subscribers("EUR") == []


async def test_a_file_database_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "bot.db"
    async with await Store.open(path) as first:
        await first.record(APP, Region.EU, rates(APP, {"EUR": "0.0355"}), at=NOW)
        await first.subscribe(7, "EUR", at=NOW)
    async with await Store.open(path) as second:
        assert (await second.state(APP, Region.EU)).rates == {"EUR": Decimal("0.0355")}
        assert await second.subscribers("EUR") == [7]
