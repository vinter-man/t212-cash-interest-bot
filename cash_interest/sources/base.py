"""What every source has in common: the Rate it produces, how it fails, and one polite GET."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, ClassVar, Final

import httpx
from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, StringConstraints, ValidationError

from cash_interest.money import pct

log = logging.getLogger(__name__)

USER_AGENT: Final = "t212-cash-interest-bot/1.0 (+https://github.com/vinter-man/t212-cash-interest-bot)"
TIMEOUT: Final = httpx.Timeout(20.0, connect=10.0)
ATTEMPTS: Final = 3
BACKOFF: Final = 2.0
# A rate outside this range is a parser reading the wrong number, not a rate.
PLAUSIBLE: Final = (Decimal(0), Decimal("0.15"))


class Region(StrEnum):
    """Who is asking: rates depend on the Trading 212 company a visitor's country is served by."""

    EU = "EU"
    UK = "UK"

    @property
    def entity(self) -> str:
        """The company code the website's data is keyed by."""
        return {Region.EU: "T212CY", Region.UK: "AVUSUK"}[self]

    @property
    def company(self) -> str:
        return {
            Region.EU: "Trading 212 Markets Ltd, CySEC",
            Region.UK: "Trading 212 UK Ltd, FCA",
        }[self]

    @property
    def storefront(self) -> str:
        """The App Store and Google Play country whose listing this region's visitors see."""
        return {Region.EU: "cy", Region.UK: "gb"}[self]


class SourceId(StrEnum):
    SITE = "site"
    CARDS = "cards"
    APP_STORE = "app_store"
    GOOGLE_PLAY = "google_play"

    @property
    def label(self) -> str:
        return {
            SourceId.SITE: "trading212.com/interest-on-cash",
            SourceId.CARDS: "trading212.com/cards",
            SourceId.APP_STORE: "App Store",
            SourceId.GOOGLE_PLAY: "Google Play",
        }[self]

    @property
    def short(self) -> str:
        """For table headers, where every character counts."""
        return {
            SourceId.SITE: "site",
            SourceId.CARDS: "cards",
            SourceId.APP_STORE: "iOS",
            SourceId.GOOGLE_PLAY: "Play",
        }[self]


def _plausible(apy: Decimal) -> Decimal:
    low, high = PLAUSIBLE
    if not low <= apy <= high:
        raise ValueError(f"{apy:%} is not a plausible rate")
    return apy


Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Apy = Annotated[Decimal, AfterValidator(_plausible)]


class Rate(BaseModel):
    """One published rate: 0.025 is 2.5% a year (AER/APY), as one source showed it to one region."""

    model_config = ConfigDict(frozen=True)

    ccy: Currency
    apy: Apy
    source: SourceId
    region: Region
    fetched_at: AwareDatetime


class FetchError(Exception):
    """A source gave no rates this time. The message is short and safe to show to a user."""


class Blocked(FetchError):
    """403, 429 or a bot check: not retried, and not asked again until the next cycle."""


class Unavailable(FetchError):
    """Network trouble or a server error that outlasted the retries."""


class ParseError(FetchError):
    """A page arrived, but no rates could be read from it."""


def to_rates(found: dict[str, Decimal], source: SourceId, region: Region, fetched_at: datetime) -> list[Rate]:
    """`found` as Rates; an implausible number fails the whole page, never just its row."""
    if not found:
        raise ParseError("no rates on the page")
    rates = []
    for ccy, apy in sorted(found.items()):
        try:
            rates.append(Rate(ccy=ccy, apy=apy, source=source, region=region, fetched_at=fetched_at))
        except ValidationError:  # the parsers pass only three-letter codes: it is the number
            raise ParseError(f"implausible rate for {ccy}: {pct(apy)}") from None
    return rates


def utcnow() -> datetime:
    return datetime.now(UTC)


def _is_bot_check(response: httpx.Response) -> bool:
    """Cloudflare's challenge and block pages, which arrive as 403 or 503."""
    if "cf-mitigated" in response.headers:
        return True
    head = response.text[:4000]
    return "Just a moment..." in head or "challenge-platform" in response.text[-4000:]


async def get(
    client: httpx.AsyncClient,
    url: str,
    *,
    attempts: int = ATTEMPTS,
    backoff: float = BACKOFF,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> bytes:
    """One GET with a short, polite retry: network errors and 5xx only, waiting 2 s, then 4 s.

    A 403 or 429 is an answer, not an accident, so it is never retried.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url)
        except httpx.TransportError as error:
            problem: FetchError = Unavailable(f"network error ({type(error).__name__})")
        else:
            if response.status_code == 200:
                return response.content
            bot_check = _is_bot_check(response)
            if response.status_code in (403, 429) or bot_check:
                kind = "bot check" if bot_check else "rate limited" if response.status_code == 429 else "refused"
                raise Blocked(f"HTTP {response.status_code}, {kind}")
            if response.status_code < 500:
                raise Unavailable(f"HTTP {response.status_code}")
            problem = Unavailable(f"HTTP {response.status_code}")
        if attempt < attempts:
            delay = backoff * 2 ** (attempt - 1)
            log.info("%s: %s, retrying in %.0f s", url, problem, delay)
            await sleep(delay)
    raise problem


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


class Source(ABC):
    """A page that publishes rates. `parse` is pure, so every parser is tested on saved pages."""

    id: ClassVar[SourceId]

    def __init__(self, client: httpx.AsyncClient, region: Region, clock: Callable[[], datetime] = utcnow) -> None:
        self.client = client
        self.region = region
        self.clock = clock

    @abstractmethod
    def url(self) -> str: ...

    @abstractmethod
    def parse(self, body: bytes, fetched_at: datetime) -> list[Rate]: ...

    async def fetch(self) -> list[Rate]:
        body = await get(self.client, self.url())
        return self.parse(body, self.clock())

    def rates(self, found: dict[str, Decimal], fetched_at: datetime) -> list[Rate]:
        return to_rates(found, self.id, self.region, fetched_at)
