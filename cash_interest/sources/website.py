"""trading212.com: /interest-on-cash and /cards.

Both are Next.js pages that ship their data with the HTML, so the rates are read from that
JSON, not from the markup. Each page carries the whole table for every Trading 212 company,
keyed by product and company code:

    "interestOnCashRates": {"invest": {"T212CY": {"EUR": 0.025, "GBP": 0.0355, …},
                                       "AVUSUK": {"EUR": 0.023, "GBP": 0.038, …}, …}, …}

The tiles a visitor sees are one company's row of it, picked by where the visitor is. Reading the
JSON means one request covers either region, and it does not depend on the server's location.

A page renders its JSON into `<script id="__NEXT_DATA__">`. If that ever moves (the app router
streams it as escaped strings in `self.__next_f.push(…)` instead), the key is looked up anywhere
in the HTML, escaped or not, before the page is called unreadable.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from cash_interest.sources.base import ParseError, Rate, Region, Source, SourceId, to_rates

KEY = "interestOnCashRates"
# The Invest account: what both pages show. ISA, SIPP and CFD rates sit beside it in the same JSON.
PRODUCT = "invest"
_NEXT_DATA = re.compile(r'<script[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _load(text: str) -> Any:
    # Decimal from the start: 0.0355 never becomes 0.035499999999999997.
    return json.loads(text, parse_float=Decimal, parse_int=Decimal)


def _embedded(html: str) -> dict[str, Any] | None:
    """The rates object wherever it is in the page: plain JSON, or a JSON string inside JS."""
    decoder = json.JSONDecoder(parse_float=Decimal, parse_int=Decimal)
    for quote in ('"', '\\"'):
        marker = f"{quote}{KEY}{quote}:"
        at = html.find(marker)
        if at < 0:
            continue
        rest = html[at + len(marker) :]
        if quote != '"':
            # Inside a JS string literal: undo one level of escaping, then read as usual.
            rest = rest[: rest.find('"])')] if '"])' in rest else rest
            rest = rest.replace('\\"', '"').replace("\\\\", "\\")
        try:
            found, _ = decoder.raw_decode(rest.lstrip())
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None


def rates_table(html: str) -> dict[str, Any]:
    """The `interestOnCashRates` object of a trading212.com page."""
    if match := _NEXT_DATA.search(html):
        try:
            data = _load(match.group(1))
        except ValueError as error:
            raise ParseError("the page's __NEXT_DATA__ is not valid JSON") from error
        table = data.get("props", {}).get("pageProps", {}).get(KEY) if isinstance(data, dict) else None
        if isinstance(table, dict):
            return table
    if (table := _embedded(html)) is not None:
        return table
    raise ParseError(f"no {KEY} on the page")


def company_rates(table: dict[str, Any], entity: str) -> dict[str, Decimal]:
    """One company's Invest rates. Promo fields (`PROMO_RATE`, …) share the object and are skipped."""
    product = table.get(PRODUCT)
    row = product.get(entity) if isinstance(product, dict) else None
    if not isinstance(row, dict):
        raise ParseError(f"no {PRODUCT} rates for {entity}")
    return {ccy: value for ccy, value in row.items() if _CURRENCY.match(ccy) and isinstance(value, Decimal)}


def page_source(html: str) -> SourceId:
    """Which page a saved file is, from its own data: for pages the owner uploads by hand."""
    match = _NEXT_DATA.search(html)
    try:
        page = _load(match.group(1)).get("page") if match else None
    except (ValueError, AttributeError):
        page = None
    for page_class in (InterestOnCash, Cards):
        if page == page_class.path:
            return page_class.id
    raise ParseError("this is not a saved trading212.com /interest-on-cash or /cards page")


def page_rates(html: str, source: SourceId, region: Region, fetched_at: datetime) -> list[Rate]:
    return to_rates(company_rates(rates_table(html), region.entity), source, region, fetched_at)


class WebsitePage(Source):
    path: str

    def url(self) -> str:
        return f"https://www.trading212.com{self.path}"

    def parse(self, body: bytes, fetched_at: datetime) -> list[Rate]:
        return page_rates(body.decode("utf-8", errors="replace"), self.id, self.region, fetched_at)


class InterestOnCash(WebsitePage):
    id = SourceId.SITE
    path = "/interest-on-cash"


class Cards(WebsitePage):
    """The card's page has its own copy of the table, with the "Earn 3.8% on your pounds" hero."""

    id = SourceId.CARDS
    path = "/cards"
