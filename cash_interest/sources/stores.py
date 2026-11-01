"""The App Store and Google Play listings, which state rates in their description:

    - High interest on your uninvested cash: 3.8% on GBP, 2.2% on EUR, 3.30% on USD, and more.

The listing is text a person edits by hand, separately from the website, so it is the copy most
likely to fall behind. It names only a few currencies; the rest are "and more".
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from decimal import Decimal

from cash_interest.sources.base import ParseError, Rate, Source, SourceId

APP_STORE_ID = "566325832"
PLAY_PACKAGE = "com.avuscapital.trading212"

# "uninvested cash" is the anchor: the same listings quote ISA and CFD figures elsewhere.
_LINE = re.compile(r"^.*\binterest\b.*\buninvested cash\b.*$", re.I | re.M)
_PAIR = re.compile(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:AER|APY)?\s*(?:on|for)\s+(?:your\s+)?([A-Z]{3})\b")
_PLAY_DESCRIPTION = re.compile(r'<div[^>]*\bdata-g-id="description"[^>]*>(.*?)</div>', re.S)
_TAG = re.compile(r"<[^>]+>")


def listing_rates(text: str) -> dict[str, Decimal]:
    """The `N% on CCY` pairs from the listing's line about uninvested cash."""
    line = _LINE.search(text)
    if line is None:
        raise ParseError("the listing has no line about interest on uninvested cash")
    # The pattern admits only digits and one separator, so Decimal() cannot fail here.
    found = {ccy: Decimal(number.replace(",", ".")) / 100 for number, ccy in _PAIR.findall(line.group(0))}
    if not found:
        raise ParseError("the interest line names no rates")
    return found


class AppStore(Source):
    """Apple's public lookup API: the listing as JSON, one storefront per call."""

    id = SourceId.APP_STORE

    def url(self) -> str:
        return f"https://itunes.apple.com/lookup?id={APP_STORE_ID}&country={self.region.storefront}"

    def parse(self, body: bytes, fetched_at: datetime) -> list[Rate]:
        try:
            data = json.loads(body)
            description = data["results"][0]["description"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ParseError("the lookup answer has no app description") from error
        if not isinstance(description, str):
            raise ParseError("the lookup answer has no app description")
        return self.rates(listing_rates(description), fetched_at)


def play_description(page: str) -> str:
    """The description as text: its own block if present, else the copy in the page's data."""
    if match := _PLAY_DESCRIPTION.search(page):
        block = match.group(1).replace("<br>", "\n").replace("<br/>", "\n")
        return html.unescape(_TAG.sub("", block))
    # The same text is also in the page's data blob, with <br> for line breaks.
    return page.replace("\\u003cbr\\u003e", "\n").replace("\\u003c", "<").replace("\\u003e", ">")


class GooglePlay(Source):
    id = SourceId.GOOGLE_PLAY

    def url(self) -> str:
        country = self.region.storefront.upper()
        return f"https://play.google.com/store/apps/details?id={PLAY_PACKAGE}&hl=en&gl={country}"

    def parse(self, body: bytes, fetched_at: datetime) -> list[Rate]:
        page = body.decode("utf-8", errors="replace")
        return self.rates(listing_rates(play_description(page)), fetched_at)
