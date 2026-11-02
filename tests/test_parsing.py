"""What people type after /rate, as a table: what it means, or the error they get back."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cash_interest.bot.parsing import InputError, parse_query

KNOWN = {"EUR", "GBP", "USD", "PLN", "CZK", "HUF", "RON", "SEK", "DKK", "NOK"}


@pytest.mark.parametrize(
    ("text", "ccy", "amount", "period"),
    [
        ("EUR 20000 5y", "EUR", "20000", "5y"),
        ("eur 20000", "EUR", "20000", "1y"),
        ("Eur 20k", "EUR", "20000", "1y"),
        ("EUR 20K 30d", "EUR", "20000", "30d"),
        ("EUR 20 000 6m", "EUR", "20000", "6m"),
        ("EUR 1 000 000", "EUR", "1000000", "1y"),
        ("€20000", "EUR", "20000", "1y"),
        ("20000€ 1y", "EUR", "20000", "1y"),
        ("€ 20000", "EUR", "20000", "1y"),
        ("£1,234.56 2w", "GBP", "1234.56", "2w"),
        ("$10", "USD", "10", "1y"),
        ("5000 zł", "PLN", "5000", "1y"),
        ("20.000,50 EUR", "EUR", "20000.50", "1y"),
        ("10.005,5 EUR", "EUR", "10005.5", "1y"),
        ("1.000.000 EUR", "EUR", "1000000", "1y"),
        ("1,5k gbp", "GBP", "1500", "1y"),
        ("0.5 usd", "USD", "0.5", "1y"),
        ("eur 2m", "EUR", "2000000", "1y"),  # the only number: millions
        ("eur 1.5m 10y", "EUR", "1500000", "10y"),
        ("gbp 20k for 5 years", "GBP", "20000", "5y"),
        ("usd 10 over 6 months", "USD", "10", "6m"),
        ("5y eur 20k", "EUR", "20000", "5y"),
        ("pln 5000 2w", "PLN", "5000", "2w"),
        ("eur, 20000, 5y", "EUR", "20000", "5y"),
        ("EUR 20000 18mo", "EUR", "20000", "18m"),
        # A three-digit period after an amount is a period, not more digits of the amount.
        ("EUR 500 365d", "EUR", "500", "365d"),
        ("EUR 1000 100d", "EUR", "1000", "100d"),
        ("EUR 5000 104w", "EUR", "5000", "104w"),
        ("EUR 20000 365 days", "EUR", "20000", "365d"),
        ("EUR 20000 120m", "EUR", "20000", "120m"),
        ("EUR 20000.00 365d", "EUR", "20000", "365d"),  # what a button sends back
        ("EUR 20 000 365d", "EUR", "20000", "365d"),
        ("usd 100 365 days", "USD", "100", "365d"),
        ("eur 999 100 weeks", "EUR", "999", "100w"),
        ("eur 20 000 18 months", "EUR", "20000", "18m"),
    ],
)
def test_understood(text: str, ccy: str, amount: str, period: str) -> None:
    query = parse_query(text, KNOWN)
    assert (query.ccy, query.amount, query.period.code) == (ccy, Decimal(amount), period)


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("", "Tell me a currency and an amount"),
        ("eur", "How much?"),
        ("20000", "Which currency?"),
        ("eru 20000", "ERU is not a currency I know. Did you mean EUR?"),
        ("xyz 20000", "XYZ is not a currency I know."),
        ("eur 20000 11y", "11y is out of range"),
        ("eur 20000 0d", "0d is out of range"),
        ("eur 0", "more than zero"),
        ("eur 200000001", "more than 100,000,000"),
        ("eur 12,34,56", "could not read 12,34,56"),
        ("eur 20000.", "could not read 20000."),
        ("eur 1234.567", "1234.567 has a fraction of a cent"),
        ("eur 0,001", "0,001 has a fraction of a cent"),
        ("eur 20k 30k", "Two amounts"),
        ("eur gbp 10", "Two currencies, EUR and GBP"),
        ("€10 gbp", "Two currencies"),
        ("eur 10 5y 6m", "Two periods, 5y and 6m"),
        ("eur 10 5y 1 year", "Two periods"),
        ("eur 20000 kr", "kr could be SEK, DKK or NOK"),
        ("eur 20k banana", "I do not understand “banana”"),
        ("eur 1.2.3", "could not read 1.2.3"),
    ],
)
def test_explained(text: str, error: str) -> None:
    with pytest.raises(InputError, match=error.replace(".", r"\.").replace("?", r"\?")):
        parse_query(text, KNOWN)


def test_a_currency_with_no_data_yet_is_still_a_currency() -> None:
    """CHF is a currency an account can hold; whether anyone quotes it is the handler's question."""
    assert parse_query("chf 1000", set()).ccy == "CHF"
