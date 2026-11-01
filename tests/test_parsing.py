"""What people type after /rate, as a table: what it means, or the error they get back."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cash_interest.bot.parsing import InputError, parse_currency, parse_query

KNOWN = {"EUR", "GBP", "USD", "PLN", "CZK", "HUF", "RON", "SEK", "DKK", "NOK"}


@pytest.mark.parametrize(
    ("text", "ccy", "amount", "period"),
    [
        ("/rate EUR 20000 5y", "EUR", "20000", "5y"),
        ("/rate eur 20000", "EUR", "20000", "1y"),
        ("/rate Eur 20k", "EUR", "20000", "1y"),
        ("/rate EUR 20K 30d", "EUR", "20000", "30d"),
        ("/rate EUR 20 000 6m", "EUR", "20000", "6m"),
        ("/rate EUR 1 000 000", "EUR", "1000000", "1y"),
        ("/rate €20000", "EUR", "20000", "1y"),
        ("/rate 20000€ 1y", "EUR", "20000", "1y"),
        ("/rate € 20000", "EUR", "20000", "1y"),
        ("/rate £1,234.56 2w", "GBP", "1234.56", "2w"),
        ("/rate $10", "USD", "10", "1y"),
        ("/rate 5000 zł", "PLN", "5000", "1y"),
        ("/rate 20.000,50 EUR", "EUR", "20000.50", "1y"),
        ("/rate 10.005,5 EUR", "EUR", "10005.5", "1y"),
        ("/rate 1.000.000 EUR", "EUR", "1000000", "1y"),
        ("/rate 1,5k gbp", "GBP", "1500", "1y"),
        ("/rate 0.5 usd", "USD", "0.5", "1y"),
        ("/rate eur 2m", "EUR", "2000000", "1y"),  # the only number: millions
        ("/rate eur 1.5m 10y", "EUR", "1500000", "10y"),
        ("/rate gbp 20k for 5 years", "GBP", "20000", "5y"),
        ("/rate usd 10 over 6 months", "USD", "10", "6m"),
        ("/rate 5y eur 20k", "EUR", "20000", "5y"),
        ("/rate@t212_cash_interest_bot pln 5000 2w", "PLN", "5000", "2w"),
        ("EUR 20000 5y", "EUR", "20000", "5y"),
        ("eur, 20000, 5y", "EUR", "20000", "5y"),
        ("/rate EUR 20000 18mo", "EUR", "20000", "18m"),
    ],
)
def test_understood(text: str, ccy: str, amount: str, period: str) -> None:
    query = parse_query(text, KNOWN)
    assert (query.ccy, query.amount, query.period.code) == (ccy, Decimal(amount), period)


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("/rate", "Tell me a currency and an amount"),
        ("/rate eur", "How much?"),
        ("/rate 20000", "Which currency?"),
        ("/rate eru 20000", "ERU is not a currency I know. Did you mean EUR?"),
        ("/rate xyz 20000", "XYZ is not a currency I know."),
        ("/rate eur 20000 11y", "11y is out of range"),
        ("/rate eur 20000 0d", "0d is out of range"),
        ("/rate eur 0", "more than zero"),
        ("/rate eur 200000001", "more than 100,000,000"),
        ("/rate eur 12,34,56", "could not read 12,34,56"),
        ("/rate eur 20000.", "could not read 20000."),
        ("/rate eur 1234.567", "1234.567 has a fraction of a cent"),
        ("/rate eur 0,001", "0,001 has a fraction of a cent"),
        ("/rate eur 20k 30k", "Two amounts"),
        ("/rate eur gbp 10", "Two currencies, EUR and GBP"),
        ("/rate €10 gbp", "Two currencies"),
        ("/rate eur 10 5y 6m", "Two periods, 5y and 6m"),
        ("/rate eur 10 5y 1 year", "Two periods"),
        ("/rate eur 20000 kr", "kr could be SEK, DKK or NOK"),
        ("/rate eur 20k banana", "I do not understand “banana”"),
        ("/rate eur 1.2.3", "could not read 1.2.3"),
    ],
)
def test_explained(text: str, error: str) -> None:
    with pytest.raises(InputError, match=error.replace(".", r"\.").replace("?", r"\?")):
        parse_query(text, KNOWN)


def test_a_currency_with_no_data_yet_is_still_a_currency() -> None:
    """CHF is a currency an account can hold; whether anyone quotes it is the handler's question."""
    assert parse_query("/rate chf 1000", set()).ccy == "CHF"


@pytest.mark.parametrize(
    ("text", "ccy"), [("/subscribe EUR", "EUR"), ("/subscribe gbp", "GBP"), ("/subscribe €", "EUR"), ("usd", "USD")]
)
def test_currency(text: str, ccy: str) -> None:
    assert parse_currency(text, KNOWN) == ccy


@pytest.mark.parametrize(("text", "error"), [("/subscribe", "One currency"), ("/subscribe eur gbp", "One currency")])
def test_currency_errors(text: str, error: str) -> None:
    with pytest.raises(InputError, match=error):
        parse_currency(text, KNOWN)
