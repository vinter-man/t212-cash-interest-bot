"""Everything a /rate reply says, worked out once: the caption and the chart only format it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cash_interest.board import Quote
from cash_interest.calc import MONTH, YEAR, Simulation, daily_interest, first_payment_day, simulate
from cash_interest.calc.period import Period


@dataclass(frozen=True, slots=True)
class Milestone:
    label: str
    day: int
    paid: Decimal


@dataclass(frozen=True, slots=True)
class Answer:
    ccy: str
    amount: Decimal
    period: Period
    quote: Quote
    start: date
    sim: Simulation
    """Day by day over the period."""
    milestones: tuple[Milestone, ...]
    """After a month, after a year and at the end of the period: a later one may be past the
    period's end (a month's answer still says what a year would earn)."""
    first_payment: int | None

    @property
    def first_day_interest(self) -> Decimal:
        return daily_interest(self.amount, self.quote.apy)

    @property
    def missed(self) -> Decimal:
        """Compounding lost to rounding down, for display: the calculation's last-digit noise
        (see Simulation.missed_compounding) never shows as a negative zero."""
        return max(self.sim.missed_compounding, Decimal(0))

    @property
    def under_a_cent(self) -> bool:
        """A day earns less than a cent, so the first payment waits."""
        return self.first_payment is not None and self.first_payment > 1


def answer(ccy: str, amount: Decimal, period: Period, quote: Quote, start: date) -> Answer:
    days = period.days(start)
    month, year = MONTH.days(start), YEAR.days(start)
    full = simulate(amount, quote.apy, max(days, year))
    milestones = [Milestone(MONTH.label, month, full.paid_by(month)), Milestone(YEAR.label, year, full.paid_by(year))]
    if days not in (month, year):
        milestones.append(Milestone(period.label, days, full.paid_by(days)))
    milestones.sort(key=lambda m: m.day)
    return Answer(
        ccy=ccy,
        amount=amount,
        period=period,
        quote=quote,
        start=start,
        sim=full.first(days),
        milestones=tuple(milestones),
        first_payment=first_payment_day(amount, quote.apy),
    )
