"""Properties that hold for every balance, rate and length, checked by hypothesis."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from cash_interest.calc import CENT, first_payment_day, simulate
from cash_interest.calc.interest import QUANTUM

balances = st.decimals(min_value=0, max_value=10_000_000, places=2, allow_nan=False, allow_infinity=False)
rates = st.decimals(min_value=0, max_value=Decimal("0.15"), places=4, allow_nan=False, allow_infinity=False)
lengths = st.integers(min_value=1, max_value=400)


@given(balances, rates, lengths)
def test_paid_plus_carried_is_what_was_accrued(balance: Decimal, apy: Decimal, days: int) -> None:
    sim = simulate(balance, apy, days)
    for day in sim.days:
        assert day.paid + day.carried == day.accrued
    assert sum(d.paid for d in sim.days) + sim.carried == sum(d.interest for d in sim.days)


@given(balances, rates, lengths)
def test_every_payment_is_whole_cents_and_never_negative(balance: Decimal, apy: Decimal, days: int) -> None:
    for day in simulate(balance, apy, days).days:
        assert day.paid >= 0
        assert day.paid % CENT == 0
        assert 0 <= day.carried < CENT


@given(balances, rates, lengths)
def test_the_balance_is_the_principal_plus_what_was_paid(balance: Decimal, apy: Decimal, days: int) -> None:
    sim = simulate(balance, apy, days)
    assert sim.balance == balance + sum(d.paid for d in sim.days)
    previous = balance
    for day in sim.days:
        assert day.balance >= previous
        previous = day.balance


@given(balances, rates, lengths)
def test_rounding_only_ever_delays_money(balance: Decimal, apy: Decimal, days: int) -> None:
    """Against paying every fraction at once: never ahead, and behind by at most what a cent a
    day would have earned. The tolerance is the 18-place rounding of each day's interest."""
    sim = simulate(balance, apy, days)
    assert sim.missed_compounding >= -days * QUANTUM / 2
    assert sim.missed_compounding <= CENT * days * sim.rate * (1 + apy) ** 2


@settings(max_examples=200)
@given(st.decimals(min_value=CENT, max_value=1000, places=2), rates.filter(lambda r: r > 0))
def test_the_first_payment_day_matches_the_simulation(balance: Decimal, apy: Decimal) -> None:
    first = first_payment_day(balance, apy)
    assert first is not None
    if first <= 400:
        days = simulate(balance, apy, first).days
        assert days[-1].paid > 0
        assert all(d.paid == 0 for d in days[:-1])
