"""Periods on the calendar: "6 months from today" is however many days those six months hold."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from cash_interest.calc.interest import MAX_DAYS

Unit = Literal["d", "w", "m", "y"]

_NAMES: dict[Unit, str] = {"d": "day", "w": "week", "m": "month", "y": "year"}
# Ten years in each unit, the longest a simulation runs.
_LIMITS: dict[Unit, int] = {"d": MAX_DAYS, "w": 521, "m": 120, "y": 10}


def add_months(start: date, months: int) -> date:
    """The same day `months` later, or the month's last day if it is shorter (31 Jan → 28 Feb)."""
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True, slots=True)
class Period:
    count: int
    unit: Unit

    def __post_init__(self) -> None:
        limit = _LIMITS[self.unit]
        if not 1 <= self.count <= limit:
            raise ValueError(f"{self.count}{self.unit} is outside 1..{limit}{self.unit}")

    def end(self, start: date) -> date:
        if self.unit in ("m", "y"):
            return add_months(start, self.count * (12 if self.unit == "y" else 1))
        return start + timedelta(days=self.count * (7 if self.unit == "w" else 1))

    def days(self, start: date) -> int:
        """How many daily payments fall in the period that begins on `start`."""
        return (self.end(start) - start).days

    @property
    def code(self) -> str:
        """`5y`: what a user types, and what a button carries."""
        return f"{self.count}{self.unit}"

    @property
    def label(self) -> str:
        name = _NAMES[self.unit]
        return f"{self.count} {name}" if self.count == 1 else f"{self.count} {name}s"


MONTH = Period(1, "m")
YEAR = Period(1, "y")
