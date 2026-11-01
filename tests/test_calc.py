"""The arithmetic against the help centre's own numbers, and the edges it does not mention."""

from __future__ import annotations

import math
from datetime import date
from decimal import ROUND_DOWN, Decimal

import pytest

from cash_interest.calc import (
    CENT,
    MAX_DAYS,
    Period,
    daily_interest,
    daily_rate,
    first_payment_day,
    simulate,
    to_cent,
)
from cash_interest.calc.interest import QUANTUM

D = Decimal


def five_places(amount: Decimal) -> Decimal:
    return amount.quantize(D("0.00001"), rounding=ROUND_DOWN)


class TestHelpCentreExample:
    """$1,000 at 5%: the worked example in "How is interest on my cash calculated and paid?"."""

    def test_daily_payment(self) -> None:
        assert five_places(daily_interest(D(1000), D("0.05"))) == D("0.13358")

    def test_first_day_pays_whole_cents_and_carries_the_rest(self) -> None:
        day = simulate(D(1000), D("0.05"), 1).days[0]
        assert day.paid == D("0.13")
        assert five_places(day.carried) == D("0.00358")
        assert day.paid + day.carried == day.accrued

    def test_three_days(self) -> None:
        """The article pays 0.13, 0.13, 0.14 and so does this. Its carries (0.00359, 0.00718,
        0.00077) come from a daily figure it rounded to 0.13359 first; the exact ones differ in
        the fifth decimal place, which is why only the payments are compared exactly."""
        days = simulate(D(1000), D("0.05"), 3).days
        assert [d.paid for d in days] == [D("0.13"), D("0.13"), D("0.14")]
        assert [round(d.carried, 4) for d in days] == [D("0.0036"), D("0.0072"), D("0.0008")]

    def test_daily_rate(self) -> None:
        assert round(daily_rate(D("0.05")), 8) == D("0.00013359")


class TestSmallBalances:
    def test_ten_dollars_at_five_percent_is_first_paid_on_day_eight(self) -> None:
        days = simulate(D(10), D("0.05"), 10).days
        assert [d.paid for d in days[:7]] == [D(0)] * 7
        assert days[7].paid == CENT
        assert first_payment_day(D(10), D("0.05")) == 8

    def test_carry_grows_until_it_makes_a_cent(self) -> None:
        days = simulate(D(10), D("0.05"), 8).days
        carried = [d.carried for d in days[:7]]
        assert carried == sorted(carried)
        assert days[6].carried < CENT <= days[7].accrued

    def test_a_cent_a_day_is_paid_on_day_one(self) -> None:
        assert first_payment_day(D(100_000), D("0.05")) == 1

    def test_first_payment_decades_away(self) -> None:
        """Ten cents at 0.25%: a simulation would stop long before the first cent."""
        assert first_payment_day(D("0.10"), D("0.0025")) == 14_629  # 40 years

    def test_one_cent_balance_at_zero_percent_is_never_paid(self) -> None:
        assert first_payment_day(CENT, D(0)) is None


class TestEdges:
    def test_zero_balance(self) -> None:
        sim = simulate(D(0), D("0.05"), 365)
        assert sim.balance == 0
        assert sim.paid == 0
        assert sim.carried == 0
        assert first_payment_day(D(0), D("0.05")) is None

    def test_zero_rate(self) -> None:
        sim = simulate(D(20_000), D(0), 365)
        assert daily_rate(D(0)) == 0
        assert sim.balance == D(20_000)
        assert all(d.paid == 0 and d.carried == 0 for d in sim.days)
        assert sim.missed_compounding == 0

    @pytest.mark.parametrize("days", [0, -1, MAX_DAYS + 1])
    def test_days_out_of_range(self, days: int) -> None:
        with pytest.raises(ValueError, match="days must be"):
            simulate(D(100), D("0.05"), days)

    def test_negative_balance(self) -> None:
        with pytest.raises(ValueError, match="balance"):
            simulate(D(-1), D("0.05"), 1)
        with pytest.raises(ValueError, match="balance"):
            daily_interest(D(-1), D("0.05"))

    def test_negative_rate(self) -> None:
        with pytest.raises(ValueError, match="rate"):
            daily_rate(D("-0.01"))

    def test_to_cent_rounds_down_never_up(self) -> None:
        assert to_cent(D("1.239999")) == D("1.23")
        assert to_cent(D("0.009999")) == D(0)
        assert to_cent(D("2.50")) == D("2.50")


class TestCompounding:
    def test_paid_interest_earns_interest(self) -> None:
        """Day 2 earns on day 1's payment too: the second day's interest is larger."""
        days = simulate(D(1_000_000), D("0.05"), 2).days
        assert days[1].interest > days[0].interest
        assert days[1].interest == pytest.approx(days[0].interest * (1 + daily_rate(D("0.05"))), rel=D("1e-6"))

    def test_carried_fraction_does_not_earn(self) -> None:
        """Day 2 earns on the balance (principal + day 1's payment), not on what was carried."""
        days = simulate(D(1000), D("0.05"), 2).days
        assert days[1].interest == daily_interest(D("1000.13"), D("0.05"))
        assert days[1].interest != daily_interest(D("1000.13") + days[0].carried, D("0.05"))

    def test_slices_agree_with_the_whole(self) -> None:
        sim = simulate(D(20_000), D("0.025"), 365)
        assert sim.paid_by(30) == sim.first(30).paid == sim.days[29].balance - D(20_000)
        assert sim.first(365) == sim
        with pytest.raises(ValueError, match="outside"):
            sim.first(366)
        with pytest.raises(ValueError, match="outside"):
            sim.paid_by(0)


class TestYears:
    """The rate compounds over 365.25 days, so the AER holds on average over four years."""

    def test_a_leap_year_earns_a_little_more_than_the_rate(self) -> None:
        leap = Period(1, "y").days(date(2027, 3, 1))  # 1 Mar 2027 → 1 Mar 2028, 29 Feb inside
        plain = Period(1, "y").days(date(2026, 3, 1))
        assert (leap, plain) == (366, 365)
        principal, apy = D(1_000_000), D("0.05")
        leap_gain = simulate(principal, apy, leap).unrounded / principal - 1
        plain_gain = simulate(principal, apy, plain).unrounded / principal - 1
        assert plain_gain < apy < leap_gain

    def test_four_years_compound_to_exactly_the_aer(self) -> None:
        sim = simulate(D(1_000_000), D("0.05"), 1461)
        assert round(sim.unrounded, 20) == round(D(1_000_000) * D("1.05") ** 4, 20)

    def test_ten_years_without_drift(self) -> None:
        """3,653 days, and no cent appears or disappears: what was paid is exactly what the
        balance grew by, every payment plus the last carry is everything the days earned, and the
        result is within rounding of the closed form."""
        principal, apy = D("20000.00"), D("0.025")
        sim = simulate(principal, apy, MAX_DAYS)
        assert all(d.paid + d.carried == d.accrued for d in sim.days)
        assert sim.balance == principal + sum(d.paid for d in sim.days)
        assert sum(d.paid for d in sim.days) + sim.carried == sum(d.interest for d in sim.days)
        # Rounding can only delay money, and never by more than what a cent per day would earn.
        assert -MAX_DAYS * QUANTUM / 2 <= sim.missed_compounding < CENT * MAX_DAYS * daily_rate(apy) * 2
        assert sim.balance == D("25602.55")

    def test_an_independent_loop_lands_on_the_same_cent(self) -> None:
        """The same rule written again, the plain way: floats, in whole cents, math.floor."""
        rate = 1.025 ** (1 / 365.25) - 1
        cents, carried = 2_000_000, 0.0
        for _ in range(MAX_DAYS):
            accrued = cents * rate + carried
            paid = math.floor(accrued)
            carried, cents = accrued - paid, cents + paid
        assert D(cents) / 100 == simulate(D("20000.00"), D("0.025"), MAX_DAYS).balance
