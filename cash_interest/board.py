"""What the sources say right now, side by side: pure functions over what the store remembers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from cash_interest.sources import ORDER, SourceId

# The currencies people ask about most come first; the rest follow alphabetically.
FIRST = ("EUR", "GBP", "USD")


@dataclass(frozen=True, slots=True)
class SourceState:
    """One source as the store remembers it."""

    source: SourceId
    rates: Mapping[str, Decimal] = field(default_factory=dict)
    """From the last successful check; empty if there has not been one."""
    ok_at: datetime | None = None
    via: str | None = None
    """How that check arrived: "http", or "upload" for a page the owner saved in a browser."""
    checked_at: datetime | None = None
    """The last check, whatever came of it."""
    failing_since: datetime | None = None
    """The first failed check after `ok_at`; None while the source is healthy."""
    problem: str | None = None
    """What the most recent failed check ran into."""

    @property
    def stale(self) -> bool:
        """It has rates, but they are older than the latest attempt to check them."""
        return self.failing_since is not None and bool(self.rates)


@dataclass(frozen=True, slots=True)
class Quote:
    source: SourceId
    apy: Decimal
    at: datetime
    stale: bool
    via: str | None = None


@dataclass(frozen=True, slots=True)
class Row:
    ccy: str
    quotes: Mapping[SourceId, Quote]

    @property
    def diverges(self) -> bool:
        """At least two sources quote this currency, and not the same number."""
        return len({quote.apy for quote in self.quotes.values()}) > 1


def currency_order(currencies: Iterable[str]) -> list[str]:
    unique = set(currencies)
    return [c for c in FIRST if c in unique] + sorted(unique - set(FIRST))


def by_currency(state: SourceState) -> dict[str, Quote]:
    """One source's quotes, keyed by currency (a Row's are keyed by source)."""
    if state.ok_at is None:
        return {}
    return {ccy: Quote(state.source, apy, state.ok_at, state.stale, state.via) for ccy, apy in state.rates.items()}


def rows(states: Mapping[SourceId, SourceState]) -> list[Row]:
    """Every currency any source quotes, each with the sources that quote it, in ORDER."""
    by_source = {source: by_currency(states[source]) for source in ORDER if source in states}
    currencies = currency_order(ccy for found in by_source.values() for ccy in found)
    return [Row(ccy, {source: found[ccy] for source, found in by_source.items() if ccy in found}) for ccy in currencies]


def pick(states: Mapping[SourceId, SourceState], ccy: str, prefer: SourceId | None = None) -> Quote | None:
    """The rate to calculate with: `prefer` if it has one, else the first fresh quote in ORDER,
    else the first stale one. A stale rate is still the last thing that source published."""
    found = [q for source in ORDER if source in states and (q := by_currency(states[source]).get(ccy))]
    for quote in found:
        if quote.source == prefer:
            return quote
    for quote in found:
        if not quote.stale:
            return quote
    return found[0] if found else None


def others(row: Row, quote: Quote) -> dict[Decimal, list[SourceId]]:
    """The rates other sources give for the same currency, grouped by value."""
    grouped: dict[Decimal, list[SourceId]] = {}
    for source, other in row.quotes.items():
        if other.apy != quote.apy:
            grouped.setdefault(other.apy, []).append(source)
    return grouped
