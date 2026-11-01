from __future__ import annotations

from decimal import Decimal

import pytest

from cash_interest.money import fraction, money, pct, pct2, whole

D = Decimal


@pytest.mark.parametrize(
    ("amount", "ccy", "text"),
    [
        (D("20000"), "EUR", "€20,000.00"),
        (D("1.355"), "GBP", "£1.36"),
        (D("0.13"), "USD", "$0.13"),
        (D("1234.5"), "PLN", "PLN 1,234.50"),
        (D("-2.5"), "EUR", "-€2.50"),
        (D("-0.001"), "EUR", "€0.00"),
    ],
)
def test_money(amount: Decimal, ccy: str, text: str) -> None:
    assert money(amount, ccy) == text


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (D("0.0046123"), "€0.0046"),
        (D("0.000036612"), "€0.000036"),
        (D("0.0099"), "€0.0099"),
        (D("0.00999"), "€0.0099"),  # cut, never rounded up to a whole cent
        (D("0.5"), "€0.50"),
        (D("1e-12"), "€0.00000000"),
        (D(0), "€0"),
    ],
)
def test_fraction(amount: Decimal, text: str) -> None:
    assert fraction(amount, "EUR") == text


def test_whole() -> None:
    assert whole(D("20000.00"), "EUR") == "€20,000"
    assert whole(D("20000.50"), "EUR") == "€20,000.50"


@pytest.mark.parametrize(
    ("apy", "short", "column"),
    [
        (D("0.025"), "2.5%", "2.50"),
        (D("0.0355"), "3.55%", "3.55"),
        (D("0.0330"), "3.3%", "3.30"),
        (D("0.03"), "3%", "3.00"),
        (D("0.0025"), "0.25%", "0.25"),
        (D(0), "0%", "0.00"),
    ],
)
def test_rates(apy: Decimal, short: str, column: str) -> None:
    assert (pct(apy), pct2(apy)) == (short, column)
