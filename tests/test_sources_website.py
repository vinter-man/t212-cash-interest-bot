"""trading212.com pages, saved from a browser on 1 November 2026 (tests/fixtures/website)."""

from __future__ import annotations

import json
import re
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from cash_interest.sources import ParseError, Region, SourceId
from cash_interest.sources.website import Cards, InterestOnCash, page_rates, page_source, rates_table
from tests.conftest import NOW, fixture

EU = {
    "CZK": "0.03", "DKK": "0.0025", "EUR": "0.025", "GBP": "0.0355", "HUF": "0.03",
    "NOK": "0.0025", "PLN": "0.0225", "RON": "0.035", "SEK": "0.005", "USD": "0.034",
}  # fmt: skip
UK = {**EU, "EUR": "0.023", "GBP": "0.038"}


def html(name: str = "interest-on-cash.html") -> str:
    return fixture(f"website/{name}").decode()


def as_dict(rates: list[object]) -> dict[str, str]:
    return {r.ccy: str(r.apy) for r in rates}  # type: ignore[attr-defined]


def parse(page: str, region: Region = Region.EU, source: SourceId = SourceId.SITE) -> dict[str, str]:
    return as_dict(page_rates(page, source, region, NOW))  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["interest-on-cash.html", "cards.html"])
@pytest.mark.parametrize(("region", "expected"), [(Region.EU, EU), (Region.UK, UK)])
def test_both_pages_both_regions(name: str, region: Region, expected: dict[str, str]) -> None:
    assert parse(html(name), region) == expected


async def test_the_source_classes_parse_their_page() -> None:
    async with httpx.AsyncClient() as client:
        site, cards = InterestOnCash(client, Region.EU), Cards(client, Region.UK)
        found = site.parse(fixture("website/interest-on-cash.html"), NOW)
        assert {(r.source, r.region, r.fetched_at) for r in found} == {(SourceId.SITE, Region.EU, NOW)}
        assert as_dict(cards.parse(fixture("website/cards.html"), NOW)) == UK  # type: ignore[arg-type]
        assert site.url() == "https://www.trading212.com/interest-on-cash"
        assert cards.url() == "https://www.trading212.com/cards"


def test_rates_are_decimals_from_the_json_not_floats() -> None:
    table = rates_table(html())
    assert table["invest"]["T212CY"]["GBP"] == Decimal("0.0355")
    assert isinstance(table["invest"]["T212CY"]["GBP"], Decimal)


def test_promo_fields_beside_the_rates_are_skipped() -> None:
    """The German company's row carries PROMO_RATE, PROMO_DURATION, …: not currencies."""
    page = html().replace('"AVUSUK":{', '"AVUSUK":{"PROMO_RATE":0.014,"PROMO_CURRENCY":"EUR","PROMO_DURATION":4,', 1)
    assert parse(page, Region.UK) == UK


def test_a_rate_of_zero_is_a_rate() -> None:
    page = html().replace('"T212CY":{"CZK":0.03', '"T212CY":{"CZK":0', 1)
    assert parse(page)["CZK"] == "0"


def test_app_router_streaming_format() -> None:
    """If the site moves to the app router, the data arrives as an escaped string inside JS."""
    table = json.dumps({"interestOnCashRates": rates_table(html())}, default=str)
    table = re.sub(r'"(0\.\d+|0)"', r"\1", table)  # Decimals back to JSON numbers
    escaped = json.dumps(f"1:{table}")[1:-1]
    page = f'<html><body><script>self.__next_f.push([1,"{escaped}"])</script></body></html>'
    assert parse(page) == EU


class TestBrokenPages:
    """What a redesign, a truncated download or a changed schema look like to the parser."""

    def test_markup_only_no_data(self) -> None:
        page = "<html><body><h1>Earn 2.5% on your EUR cash</h1><p>EUR</p><p>2.5%</p></body></html>"
        with pytest.raises(ParseError, match="no interestOnCashRates"):
            parse(page)

    def test_truncated_in_the_middle_of_the_json(self) -> None:
        page = html()
        with pytest.raises(ParseError):
            parse(page[: page.index('"T212CY"') + 20])

    def test_next_data_is_not_json(self) -> None:
        page = html().replace('{"props"', "{props", 1)
        with pytest.raises(ParseError, match="not valid JSON"):
            parse(page)

    def test_the_key_was_renamed(self) -> None:
        with pytest.raises(ParseError, match="no interestOnCashRates"):
            parse(html().replace("interestOnCashRates", "cashRates"))

    def test_the_company_is_missing(self) -> None:
        with pytest.raises(ParseError, match="no invest rates for T212CY"):
            parse(html().replace('"T212CY"', '"T212XX"'))

    def test_the_product_is_not_an_object(self) -> None:
        page = re.sub(r'"interestOnCashRates":\{"invest":', '"interestOnCashRates":{"invest":[],"x":', html())
        with pytest.raises(ParseError, match="no invest rates"):
            parse(page)

    def test_a_row_with_no_currencies(self) -> None:
        page = re.sub(r'"T212CY":\{[^}]*\}', '"T212CY":{"PROMO_DURATION":4}', html(), count=1)
        with pytest.raises(ParseError, match="no rates on the page"):
            parse(page)

    def test_an_implausible_rate_fails_the_whole_page(self) -> None:
        """25% is a parser reading the wrong field: no rate from this page is trusted."""
        page = html().replace('"T212CY":{"CZK":0.03', '"T212CY":{"CZK":0.25', 1)
        with pytest.raises(ParseError) as caught:
            parse(page)
        assert str(caught.value) == "implausible rate for CZK: 25%"

    def test_a_bug_is_not_blamed_on_the_page(self) -> None:
        """Only the number can be implausible; a naive timestamp is the caller's mistake."""
        with pytest.raises(ValidationError, match="fetched_at"):
            page_rates(html(), SourceId.SITE, Region.EU, NOW.replace(tzinfo=None))

    def test_a_rate_written_as_text(self) -> None:
        page = html().replace('"T212CY":{"CZK":0.03', '"T212CY":{"CZK":"3%"', 1)
        assert "CZK" not in parse(page)

    def test_empty_page(self) -> None:
        with pytest.raises(ParseError):
            parse("")

    def test_a_block_page_is_not_mistaken_for_data(self) -> None:
        with pytest.raises(ParseError):
            parse(html("cloudflare-access-denied.html"))


class TestSavedPages:
    """The owner can send the bot a page saved in a browser; the page says which one it is."""

    @pytest.mark.parametrize(
        ("name", "source"), [("interest-on-cash.html", SourceId.SITE), ("cards.html", SourceId.CARDS)]
    )
    def test_recognised(self, name: str, source: SourceId) -> None:
        assert page_source(html(name)) is source

    @pytest.mark.parametrize(
        "page",
        [
            "<html>not a saved page</html>",
            '<script id="__NEXT_DATA__" type="application/json">{"page":"/invest"}</script>',
            '<script id="__NEXT_DATA__" type="application/json">{broken</script>',
            '<script id="__NEXT_DATA__" type="application/json">[1, 2]</script>',
        ],
    )
    def test_anything_else_is_refused(self, page: str) -> None:
        with pytest.raises(ParseError, match=r"not a saved trading212\.com"):
            page_source(page)
