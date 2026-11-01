"""The real sources, today. Run by the nightly workflow (`pytest -m live`), never by default.

Fails when a source answers but its parser finds nothing, or finds a rate outside 0–15%: that is
a page that changed under the parser, and the workflow opens an issue for it. trading212.com
answers non-browser clients with a Cloudflare bot check; that is skipped, not failed, because
it says nothing about the parser — the saved pages in tests/fixtures cover that.

Each URL is requested once per run however many tests read it: six requests a night in all.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cash_interest.sources import SOURCES, Blocked, FetchError, Region, SourceId, http_client, utcnow
from cash_interest.sources.base import get

pytestmark = pytest.mark.live

WEBSITE = (SourceId.SITE, SourceId.CARDS)
_answers: dict[str, bytes | FetchError] = {}


async def once(url: str) -> bytes:
    if url not in _answers:
        async with http_client() as client:
            try:
                _answers[url] = await get(client, url)
            except FetchError as error:
                _answers[url] = error
    answer = _answers[url]
    if isinstance(answer, FetchError):
        raise answer
    return answer


@pytest.mark.parametrize("region", list(Region))
@pytest.mark.parametrize("source_id", list(SourceId))
async def test_source_still_parses(source_id: SourceId, region: Region) -> None:
    async with http_client() as client:
        source = SOURCES[source_id](client, region)
        try:
            body = await once(source.url())
        except Blocked as error:
            if source_id in WEBSITE:
                pytest.skip(f"{source_id}: {error} (trading212.com challenges non-browser clients)")
            raise
        found = source.parse(body, utcnow())
    assert found, f"{source_id} answered, but its parser found no rates"
    for rate in found:
        assert Decimal(0) <= rate.apy <= Decimal("0.15"), f"{source_id} {rate.ccy}: {rate.apy:%} is out of range"
    if source_id not in WEBSITE:
        # The listings have always named these three; if one drops out, a person should look.
        assert {"EUR", "GBP", "USD"} <= {r.ccy for r in found}
