"""The daily interest rule Trading 212 publishes, as arithmetic and nothing else.

Help centre, "How is interest on my cash calculated and paid?":

    daily rate = (1 + AER) ** (1 / 365.25) - 1
    each day:  accrued = balance × daily rate + what was carried from yesterday
               paid    = accrued, rounded down to the cent
               carried = accrued - paid        (kept for tomorrow; it earns nothing itself)
               balance = balance + paid        (interest lands as cash, so it compounds)

Every amount is a Decimal. The daily rate is worked out to 50 significant digits and each day's
interest kept to 18 decimal places, so every amount here is exact in Python's default 28-digit
context too: `paid + carried` is `accrued` wherever it is checked, and ten years of days cannot
drift by anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, Context, Decimal, localcontext

DAYS_PER_YEAR = Decimal("365.25")
CENT = Decimal("0.01")
# Interest is kept to 1e-18 of a currency unit: nine integer digits (balances up to 10^8, grown
# for ten years) plus eighteen decimals fit the default context's 28 digits.
QUANTUM = Decimal("1e-18")
# Ten calendar years are 3,652 or 3,653 days, depending on how many 29 Februaries they hold.
MAX_DAYS = 3653

_PRECISION = Context(prec=50)


def daily_rate(apy: Decimal) -> Decimal:
    """The rate for one day that compounds to `apy` over 365.25 days."""
    if apy < 0:
        raise ValueError(f"a rate cannot be negative: {apy}")
    with localcontext(_PRECISION):
        return (1 + apy) ** (1 / DAYS_PER_YEAR) - 1


def _interest(balance: Decimal, rate: Decimal) -> Decimal:
    with localcontext(_PRECISION):
        return (balance * rate).quantize(QUANTUM)


def daily_interest(balance: Decimal, apy: Decimal) -> Decimal:
    """What one day earns on `balance`, before rounding: the help centre's DP."""
    if balance < 0:
        raise ValueError(f"a balance cannot be negative: {balance}")
    return _interest(balance, daily_rate(apy))


def to_cent(amount: Decimal) -> Decimal:
    """Rounded down to the cent, as every payment is."""
    return amount.quantize(CENT, rounding=ROUND_DOWN)


def first_payment_day(balance: Decimal, apy: Decimal) -> int | None:
    """The day the first cent arrives, counting from 1; None if it never does.

    Nothing is paid before then, so the balance stays put and each day adds the same interest:
    the first payment is on the first day `n` with `n × DP ≥ 0.01`. Exact, and it answers for
    balances so small that the first cent is decades away, where a simulation would stop first.
    """
    interest = daily_interest(balance, apy)
    if interest == 0:
        return None
    with localcontext(_PRECISION):
        return int((CENT / interest).to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True, slots=True)
class Day:
    n: int
    """1 for the first day."""
    interest: Decimal
    """The balance times the daily rate: what this day earned."""
    accrued: Decimal
    """`interest` plus what was carried in from the day before."""
    paid: Decimal
    """`accrued` rounded down to the cent: what reached the balance."""
    carried: Decimal
    """`accrued - paid`: the fraction of a cent kept for tomorrow."""
    balance: Decimal
    """After this day's payment."""


@dataclass(frozen=True, slots=True)
class Simulation:
    principal: Decimal
    apy: Decimal
    rate: Decimal
    """The daily rate."""
    days: tuple[Day, ...]

    @property
    def balance(self) -> Decimal:
        return self.days[-1].balance if self.days else self.principal

    @property
    def paid(self) -> Decimal:
        return self.balance - self.principal

    @property
    def carried(self) -> Decimal:
        """Earned but not paid yet: it arrives once the running total reaches a cent."""
        return self.days[-1].carried if self.days else Decimal(0)

    def paid_by(self, day: int) -> Decimal:
        """Interest paid over the first `day` days."""
        return self.first(day).paid

    def first(self, days: int) -> Simulation:
        """The same simulation, stopped after `days` days."""
        if not 1 <= days <= len(self.days):
            raise ValueError(f"day {days} is outside 1..{len(self.days)}")
        return Simulation(self.principal, self.apy, self.rate, self.days[:days])

    @property
    def unrounded(self) -> Decimal:
        """The balance if every fraction of a cent were paid the day it was earned."""
        with localcontext(_PRECISION):
            return self.principal * (1 + self.rate) ** len(self.days)

    @property
    def missed_compounding(self) -> Decimal:
        """Interest the carried fractions would have earned, had they been paid at once.

        This is what rounding down really costs: unlike `carried`, which is only late, it is
        never paid. Zero or more, give or take half a QUANTUM a day: the days keep their interest
        to 18 places, the closed form does not.
        """
        with localcontext(_PRECISION):
            return self.unrounded - self.balance - self.carried


def simulate(principal: Decimal, apy: Decimal, days: int) -> Simulation:
    """Day by day, the way the payments arrive."""
    if principal < 0:
        raise ValueError(f"a balance cannot be negative: {principal}")
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_DAYS}, not {days}")
    rate = daily_rate(apy)
    balance, carried = principal, Decimal(0)
    out: list[Day] = []
    for n in range(1, days + 1):
        interest = _interest(balance, rate)
        accrued = interest + carried
        paid = to_cent(accrued)
        carried = accrued - paid
        balance += paid
        out.append(Day(n, interest, accrued, paid, carried, balance))
    return Simulation(principal, apy, rate, tuple(out))
