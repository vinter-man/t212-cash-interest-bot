from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from cash_interest.board import SourceState, currency_order, others, pick, rows
from cash_interest.sources import SourceId
from tests.conftest import NOW, SITE_EU, STORE_EU, state

SITE, CARDS, APP, PLAY = SourceId.SITE, SourceId.CARDS, SourceId.APP_STORE, SourceId.GOOGLE_PLAY


def test_currency_order() -> None:
    assert currency_order(["PLN", "USD", "CZK", "EUR", "EUR"]) == ["EUR", "USD", "CZK", "PLN"]


def test_rows_mark_where_sources_disagree(states: dict[SourceId, SourceState]) -> None:
    table = {row.ccy: row for row in rows(states)}
    assert list(table) == ["EUR", "GBP", "USD", "CZK", "PLN"]
    assert table["EUR"].diverges
    assert not table["PLN"].diverges  # only the website quotes it
    assert list(table["EUR"].quotes) == [SITE, CARDS, APP, PLAY]
    assert list(table["PLN"].quotes) == [SITE, CARDS]


def test_a_source_that_never_answered_quotes_nothing() -> None:
    states = {SITE: SourceState(SITE), APP: state(APP, STORE_EU)}
    assert [list(row.quotes) for row in rows(states)] == [[APP]] * 3


def test_pick_prefers_the_website() -> None:
    states = {SITE: state(SITE, SITE_EU), APP: state(APP, STORE_EU)}
    quote = pick(states, "EUR")
    assert quote is not None
    assert (quote.source, quote.apy) == (SITE, Decimal("0.025"))


def test_pick_prefers_fresh_over_stale() -> None:
    stale_site = state(SITE, SITE_EU, failing_since=NOW + timedelta(hours=6), problem="HTTP 403")
    states = {SITE: stale_site, APP: state(APP, STORE_EU)}
    assert pick(states, "EUR").source == APP  # type: ignore[union-attr]
    stale = pick(states, "PLN")  # only the stale website has it: still better than nothing
    assert stale is not None
    assert (stale.source, stale.stale) == (SITE, True)


def test_pick_takes_the_source_asked_for(states: dict[SourceId, SourceState]) -> None:
    assert pick(states, "EUR", prefer=PLAY).source == PLAY  # type: ignore[union-attr]
    assert pick(states, "PLN", prefer=PLAY).source == SITE  # type: ignore[union-attr]
    assert pick(states, "CHF") is None


def test_others_are_grouped_by_value(states: dict[SourceId, SourceState]) -> None:
    row = next(r for r in rows(states) if r.ccy == "EUR")
    quote = pick(states, "EUR")
    assert quote is not None
    assert others(row, quote) == {Decimal("0.022"): [APP, PLAY]}
