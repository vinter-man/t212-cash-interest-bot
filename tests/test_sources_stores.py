"""App Store and Google Play listings, saved on 1 November 2026 (tests/fixtures/stores)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest

from cash_interest.sources import ParseError, Region, SourceId
from cash_interest.sources.stores import AppStore, GooglePlay, listing_rates, play_description
from tests.conftest import NOW, fixture

LISTED = {"EUR": Decimal("0.022"), "GBP": Decimal("0.038"), "USD": Decimal("0.033")}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as opened:
        yield opened


class TestListingLine:
    def test_the_line_as_published(self) -> None:
        line = "- High interest on your uninvested cash: 3.8% on GBP, 2.2% on EUR, 3.30% on USD, and more."
        assert listing_rates(line) == LISTED

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("Interest on uninvested cash: 3,8 % on GBP", {"GBP": Decimal("0.038")}),
            ("Earn interest on uninvested cash — 4.1% AER on GBP", {"GBP": Decimal("0.041")}),
            ("interest on UNINVESTED CASH: 2% for your EUR", {"EUR": Decimal("0.02")}),
        ],
    )
    def test_small_rewordings(self, line: str, expected: dict[str, Decimal]) -> None:
        assert listing_rates(line) == expected

    def test_other_percentages_in_the_listing_are_ignored(self) -> None:
        text = (
            "77% of retail CFD accounts lose money.\n- 3.60% AER on cash ISA\n"
            "- Interest on uninvested cash: 3.8% on GBP"
        )
        assert listing_rates(text) == {"GBP": Decimal("0.038")}

    def test_no_interest_line(self) -> None:
        with pytest.raises(ParseError, match="no line about interest"):
            listing_rates("Commission-free trading. 77% of retail CFD accounts lose money.")

    def test_a_line_without_rates(self) -> None:
        with pytest.raises(ParseError, match="names no rates"):
            listing_rates("High interest on your uninvested cash, paid daily.")


class TestAppStore:
    @pytest.mark.parametrize(("region", "storefront"), [(Region.EU, "cy"), (Region.UK, "gb")])
    async def test_listing(self, client: httpx.AsyncClient, region: Region, storefront: str) -> None:
        source = AppStore(client, region)
        found = source.parse(fixture(f"stores/app-store-{storefront}.json"), NOW)
        assert {r.ccy: r.apy for r in found} == LISTED
        assert {(r.source, r.region) for r in found} == {(SourceId.APP_STORE, region)}
        assert source.url().endswith(f"id=566325832&country={storefront}")

    async def test_the_german_listing_has_no_english_line(self, client: httpx.AsyncClient) -> None:
        with pytest.raises(ParseError, match="no line about interest"):
            AppStore(client, Region.EU).parse(fixture("stores/app-store-de.json"), NOW)

    @pytest.mark.parametrize(
        "body",
        [
            b'{"resultCount": 0, "results": []}',
            b"<html>Service Unavailable</html>",
            b'{"results": [{"description": 7}]}',
        ],
    )
    async def test_broken_answers(self, client: httpx.AsyncClient, body: bytes) -> None:
        with pytest.raises(ParseError, match="no app description"):
            AppStore(client, Region.EU).parse(body, NOW)

    async def test_a_reworded_listing(self, client: httpx.AsyncClient) -> None:
        data = json.loads(fixture("stores/app-store-cy.json"))
        data["results"][0]["description"] = data["results"][0]["description"].replace("uninvested cash", "idle cash")
        with pytest.raises(ParseError):
            AppStore(client, Region.EU).parse(json.dumps(data).encode(), NOW)


class TestGooglePlay:
    @pytest.mark.parametrize(("region", "country"), [(Region.EU, "cy"), (Region.UK, "gb")])
    async def test_listing(self, client: httpx.AsyncClient, region: Region, country: str) -> None:
        source = GooglePlay(client, region)
        found = source.parse(fixture(f"stores/google-play-{country}.html"), NOW)
        assert {r.ccy: r.apy for r in found} == LISTED
        assert source.url().endswith(f"&hl=en&gl={country.upper()}")

    def test_description_block_becomes_text(self) -> None:
        text = play_description(fixture("stores/google-play-cy.html").decode())
        assert "- High interest on your uninvested cash: 3.8% on GBP" in text
        assert "<br>" not in text
        assert "UK's #1 app" in text  # &#39; unescaped

    async def test_falls_back_to_the_data_blob(self, client: httpx.AsyncClient) -> None:
        """Without the description block, the same text is read from the page's data."""
        page = fixture("stores/google-play-cy.html").decode().replace('data-g-id="description"', 'data-g-id="x"')
        found = GooglePlay(client, Region.EU).parse(page.encode(), NOW)
        assert {r.ccy: r.apy for r in found} == LISTED

    async def test_a_redesigned_page_without_the_text(self, client: httpx.AsyncClient) -> None:
        page = b"<html><body><div data-g-id='description'>A great app.</div></body></html>"
        with pytest.raises(ParseError):
            GooglePlay(client, Region.EU).parse(page, NOW)
