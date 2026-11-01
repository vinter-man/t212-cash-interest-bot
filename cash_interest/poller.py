"""One polling cycle: ask every source once, remember the answers, report what changed.

A failed check is recorded and nothing else happens: the last good rates stay on show, marked
stale, and nobody is notified. Only a successful check that disagrees with the previous
successful live check of the same source is a change, so a parser that breaks, a page that is
blocked, a page the owner sends, or a currency that drops out of a listing never sends an alert.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from cash_interest.sources import Blocked, FetchError, ParseError, Source, SourceId, Unavailable
from cash_interest.store import Change, Status, Store

log = logging.getLogger(__name__)

Notify = Callable[[Sequence[Change]], Awaitable[None]]


@dataclass(slots=True)
class Report:
    found: dict[SourceId, int] = field(default_factory=dict)
    failed: dict[SourceId, str] = field(default_factory=dict)
    changes: list[Change] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{source}: {count} rates" for source, count in self.found.items()]
        parts += [f"{source}: {problem}" for source, problem in self.failed.items()]
        return "; ".join(parts) + f"; {len(self.changes)} changed"


def status_of(error: FetchError) -> Status:
    if isinstance(error, Blocked):
        return Status.BLOCKED
    if isinstance(error, Unavailable):
        return Status.UNAVAILABLE
    if isinstance(error, ParseError):
        return Status.PARSE_ERROR
    return Status.ERROR


async def poll(
    store: Store,
    sources: Iterable[Source],
    clock: Callable[[], datetime],
    notify: Notify | None = None,
) -> Report:
    """Every source once, one after another: one request each, never two at once to one host."""
    report = Report()
    for source in sources:
        try:
            rates = await source.fetch()
        except FetchError as error:
            report.failed[source.id] = str(error)
            log.warning("%s: %s", source.id, error)
            await store.record_failure(source.id, source.region, status_of(error), str(error), at=clock())
            continue
        except Exception as error:  # a parser bug must cost one source one cycle, not the poller
            report.failed[source.id] = f"unexpected {type(error).__name__}"
            log.exception("%s: unexpected error", source.id)
            await store.record_failure(source.id, source.region, Status.ERROR, type(error).__name__, at=clock())
            continue
        try:
            changes = await store.record(source.id, source.region, rates, at=rates[0].fetched_at)
        except Exception:  # the database, not the source: the other sources still get their turn
            report.failed[source.id] = "not recorded"
            log.exception("%s: could not record the rates", source.id)
            continue
        report.found[source.id] = len(rates)
        report.changes += changes
        for change in changes:
            log.info("%s %s: %s -> %s", source.id, change.ccy, change.old, change.new)
    log.info("poll: %s", report.summary())
    if report.changes and notify is not None:
        await notify(report.changes)
    return report
