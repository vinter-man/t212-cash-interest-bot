"""The one GET every source makes: what is retried, what is not, and how a block is recognised."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from cash_interest.sources import Blocked, ParseError, Region, SourceId, Unavailable, all_sources, http_client
from cash_interest.sources.base import USER_AGENT, get
from tests.conftest import NOW, fixture

URL = "https://example.test/page"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with http_client() as opened:
        yield opened


async def fetch(client: httpx.AsyncClient) -> bytes:
    return await get(client, URL, backoff=0)


@respx.mock
async def test_ok(client: httpx.AsyncClient) -> None:
    route = respx.get(URL).respond(200, content=b"hello")
    assert await fetch(client) == b"hello"
    assert route.calls.last.request.headers["User-Agent"] == USER_AGENT


@respx.mock
@pytest.mark.parametrize(("status", "kind"), [(403, "refused"), (429, "rate limited")])
async def test_refusals_are_not_retried(client: httpx.AsyncClient, status: int, kind: str) -> None:
    route = respx.get(URL).respond(status)
    with pytest.raises(Blocked, match=f"HTTP {status}, {kind}"):
        await fetch(client)
    assert route.call_count == 1


@respx.mock
@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("cloudflare-access-denied.html", 403),
        ("cloudflare-challenge.html", 403),  # as it was saved
        ("cloudflare-challenge.html", 503),  # the same page as a 503 must not be retried either
    ],
)
async def test_cloudflare_pages_are_a_bot_check(client: httpx.AsyncClient, name: str, status: int) -> None:
    route = respx.get(URL).respond(status, content=fixture(f"website/{name}"))
    with pytest.raises(Blocked, match="bot check"):
        await fetch(client)
    assert route.call_count == 1


@respx.mock
async def test_cloudflare_header_alone_is_enough(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(503, headers={"cf-mitigated": "challenge"})
    with pytest.raises(Blocked, match="bot check"):
        await fetch(client)


@respx.mock
async def test_a_server_error_is_retried_then_succeeds(client: httpx.AsyncClient) -> None:
    route = respx.get(URL).mock(side_effect=[httpx.Response(502), httpx.Response(200, content=b"ok")])
    assert await fetch(client) == b"ok"
    assert route.call_count == 2


@respx.mock
async def test_three_attempts_then_unavailable(client: httpx.AsyncClient) -> None:
    route = respx.get(URL).respond(500)
    with pytest.raises(Unavailable, match="HTTP 500"):
        await fetch(client)
    assert route.call_count == 3


@respx.mock
async def test_network_errors_are_retried(client: httpx.AsyncClient) -> None:
    route = respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(Unavailable, match="ConnectTimeout"):
        await fetch(client)
    assert route.call_count == 3


@respx.mock
async def test_not_found_is_not_retried(client: httpx.AsyncClient) -> None:
    route = respx.get(URL).respond(404)
    with pytest.raises(Unavailable, match="HTTP 404"):
        await fetch(client)
    assert route.call_count == 1


@respx.mock
async def test_backoff_doubles(client: httpx.AsyncClient) -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    respx.get(URL).respond(500)
    with pytest.raises(Unavailable):
        await get(client, URL, sleep=sleep)
    assert waits == [2.0, 4.0]


@respx.mock
async def test_every_source_end_to_end(client: httpx.AsyncClient) -> None:
    """Each source asks its own URL once and turns the saved answer into rates."""
    pages = {
        "https://www.trading212.com/interest-on-cash": fixture("website/interest-on-cash.html"),
        "https://www.trading212.com/cards": fixture("website/cards.html"),
        "https://itunes.apple.com/lookup": fixture("stores/app-store-cy.json"),
        "https://play.google.com/store/apps/details": fixture("stores/google-play-cy.html"),
    }
    routes = [respx.get(url__startswith=url).respond(200, content=body) for url, body in pages.items()]
    sources = all_sources(client, Region.EU, clock=lambda: NOW)
    found = {source.id: await source.fetch() for source in sources}
    assert [len(found[s]) for s in SourceId] == [10, 10, 3, 3]
    assert all(route.call_count == 1 for route in routes)
    assert all(rate.fetched_at == NOW for rates in found.values() for rate in rates)


@respx.mock
async def test_a_page_that_arrives_but_says_nothing(client: httpx.AsyncClient) -> None:
    respx.get(url__startswith="https://www.trading212.com/").respond(200, content=b"<html></html>")
    site = all_sources(client, Region.EU)[0]
    with pytest.raises(ParseError):
        await site.fetch()
