"""SQLite: every check of every source, the rates each successful one found, and subscriptions.

A check is a row in `checks` whatever its outcome, so "last checked", "stale since" and the rate
history all come from one table. Rates are stored as text: a Decimal goes in and comes out as the
same Decimal, never as a float.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Self

import aiosqlite

from cash_interest.board import SourceState
from cash_interest.sources import ORDER, Rate, Region, SourceId

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id      INTEGER PRIMARY KEY,
    source  TEXT NOT NULL,
    region  TEXT NOT NULL,
    at      TEXT NOT NULL,
    status  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT '',
    via     TEXT NOT NULL DEFAULT 'http'
);
CREATE INDEX IF NOT EXISTS checks_by_source ON checks (source, region, id);
CREATE TABLE IF NOT EXISTS rates (
    check_id INTEGER NOT NULL REFERENCES checks (id) ON DELETE CASCADE,
    ccy      TEXT NOT NULL,
    apy      TEXT NOT NULL,
    PRIMARY KEY (check_id, ccy)
);
CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id INTEGER NOT NULL,
    ccy     TEXT NOT NULL,
    since   TEXT NOT NULL,
    PRIMARY KEY (chat_id, ccy)
);
"""


class Status(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    PARSE_ERROR = "parse_error"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Change:
    """A source now publishes a different rate than at its previous successful check."""

    source: SourceId
    region: Region
    ccy: str
    old: Decimal
    new: Decimal
    at: datetime


class Store:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        # One connection, shared by the poller and the handlers: a check and its rates, and the
        # comparison with the previous check, must not interleave with another write.
        self._writing = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path | str) -> Self:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(path)
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.executescript(SCHEMA)
        await db.commit()
        return cls(db)

    async def close(self) -> None:
        await self.db.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.close()

    async def _write(self, sql: str, params: tuple[object, ...]) -> aiosqlite.Cursor:
        """One statement in its own transaction."""
        async with self._writing:
            cursor = await self.db.execute(sql, params)
            await self.db.commit()
            return cursor

    async def _last_ok(self, source: SourceId, region: Region, via: str | None = None) -> tuple[int, str, str] | None:
        """The latest successful check, or the latest that arrived `via` "http" or "upload"."""
        cursor = await self.db.execute(
            "SELECT id, at, via FROM checks WHERE source = ? AND region = ? AND status = 'ok' "
            "AND (? IS NULL OR via = ?) ORDER BY id DESC LIMIT 1",
            (source, region, via, via),
        )
        row = await cursor.fetchone()
        return (int(row[0]), str(row[1]), str(row[2])) if row else None

    async def _rates(self, check_id: int) -> dict[str, Decimal]:
        cursor = await self.db.execute("SELECT ccy, apy FROM rates WHERE check_id = ?", (check_id,))
        return {str(ccy): Decimal(apy) for ccy, apy in await cursor.fetchall()}

    async def record(
        self, source: SourceId, region: Region, rates: Sequence[Rate], *, at: datetime, via: str = "http"
    ) -> list[Change]:
        """A successful check. Returns what changed since the previous one: a currency seen for the
        first time, or one the source stopped listing, is not a change.

        A live check is compared with the previous live check, never with a saved page: a page of
        unknown age in between must not turn into a second alert for a change already reported.
        A saved page is compared with whatever was last on show, because that is what its sender
        wants to know.
        """
        if any(r.source != source or r.region != region for r in rates):
            raise ValueError(f"rates from another source or region recorded as {source}/{region}")
        async with self._writing:
            previous = await self._last_ok(source, region, via="http" if via == "http" else None)
            before = await self._rates(previous[0]) if previous else {}
            try:
                cursor = await self.db.execute(
                    "INSERT INTO checks (source, region, at, status, via) VALUES (?, ?, ?, 'ok', ?)",
                    (source, region, at.isoformat(), via),
                )
                await self.db.executemany(
                    "INSERT INTO rates (check_id, ccy, apy) VALUES (?, ?, ?)",
                    [(cursor.lastrowid, r.ccy, str(r.apy.normalize())) for r in rates],
                )
                await self.db.commit()
            except BaseException:
                # A check without its rates would become the baseline for the next comparison.
                await self.db.rollback()
                raise
        return [
            Change(source, region, r.ccy, before[r.ccy], r.apy, at)
            for r in rates
            if r.ccy in before and before[r.ccy] != r.apy
        ]

    async def record_failure(
        self, source: SourceId, region: Region, status: Status, detail: str, *, at: datetime
    ) -> None:
        if status is Status.OK:
            raise ValueError("a failure needs a failing status")
        await self._write(
            "INSERT INTO checks (source, region, at, status, detail) VALUES (?, ?, ?, ?, ?)",
            (source, region, at.isoformat(), status, detail),
        )

    async def state(self, source: SourceId, region: Region) -> SourceState:
        cursor = await self.db.execute(
            "SELECT at, status, detail FROM checks WHERE source = ? AND region = ? ORDER BY id DESC LIMIT 1",
            (source, region),
        )
        latest = await cursor.fetchone()
        if latest is None:
            return SourceState(source)
        ok = await self._last_ok(source, region)
        cursor = await self.db.execute(
            "SELECT at FROM checks WHERE source = ? AND region = ? AND id > ? ORDER BY id LIMIT 1",
            (source, region, ok[0] if ok else 0),
        )
        first_failure = await cursor.fetchone()
        failing = latest[1] != Status.OK
        return SourceState(
            source=source,
            rates=await self._rates(ok[0]) if ok else {},
            ok_at=datetime.fromisoformat(ok[1]) if ok else None,
            via=ok[2] if ok else None,
            checked_at=datetime.fromisoformat(latest[0]),
            failing_since=datetime.fromisoformat(first_failure[0]) if failing and first_failure else None,
            problem=str(latest[2]) if failing else None,
        )

    async def states(self, region: Region) -> dict[SourceId, SourceState]:
        return {source: await self.state(source, region) for source in ORDER}

    async def last_check(self, region: Region, via: str = "http") -> datetime | None:
        """When the poller last ran for this region, so a restart does not poll again early."""
        cursor = await self.db.execute("SELECT MAX(at) FROM checks WHERE region = ? AND via = ?", (region, via))
        row = await cursor.fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    async def subscribe(self, chat_id: int, ccy: str, *, at: datetime) -> bool:
        """True if this is a new subscription."""
        cursor = await self._write(
            "INSERT OR IGNORE INTO subscriptions (chat_id, ccy, since) VALUES (?, ?, ?)",
            (chat_id, ccy, at.isoformat()),
        )
        return cursor.rowcount == 1

    async def unsubscribe(self, chat_id: int, ccy: str) -> bool:
        """True if there was a subscription to remove."""
        cursor = await self._write("DELETE FROM subscriptions WHERE chat_id = ? AND ccy = ?", (chat_id, ccy))
        return cursor.rowcount == 1

    async def forget(self, chat_id: int) -> int:
        """Drop every subscription of a chat that blocked the bot or no longer exists."""
        cursor = await self._write("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))
        return cursor.rowcount

    async def subscriptions(self, chat_id: int) -> list[str]:
        cursor = await self.db.execute("SELECT ccy FROM subscriptions WHERE chat_id = ? ORDER BY ccy", (chat_id,))
        return [str(row[0]) for row in await cursor.fetchall()]

    async def subscribers(self, ccy: str) -> list[int]:
        cursor = await self.db.execute("SELECT chat_id FROM subscriptions WHERE ccy = ? ORDER BY chat_id", (ccy,))
        return [int(row[0]) for row in await cursor.fetchall()]
