"""The chart is checked for what can be checked without eyes: it renders, the same way every time,
for every shape of answer. The README screenshots are where it is looked at."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from cash_interest.answer import answer
from cash_interest.board import Quote
from cash_interest.calc import Period
from cash_interest.charts import rate_chart
from cash_interest.sources import Region, SourceId
from tests.conftest import TODAY

PNG = b"\x89PNG\r\n\x1a\n"
AT = datetime(2026, 11, 1, 20, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("ccy", "amount", "apy", "period"),
    [
        ("EUR", "20000", "0.025", Period(5, "y")),  # the README's example
        ("USD", "10", "0.033", Period(30, "d")),  # under a cent a day: the cups fill up
        ("DKK", "1000", "0", Period(1, "y")),  # 0%: a flat line and a note
        ("SEK", "0.10", "0.005", Period(1, "w")),  # the first cent is years away
        ("GBP", "99999999.99", "0.15", Period(10, "y")),  # the widest numbers
    ],
)
def test_renders(ccy: str, amount: str, apy: str, period: Period) -> None:
    result = answer(ccy, Decimal(amount), period, Quote(SourceId.SITE, Decimal(apy), AT, False), TODAY)
    png = rate_chart(result, Region.EU)
    assert png.startswith(PNG)
    assert len(png) > 20_000


def test_the_same_answer_draws_the_same_picture() -> None:
    """The pencil wobble is seeded, so a chart is reproducible byte for byte."""
    result = answer("EUR", Decimal(500), Period(6, "m"), Quote(SourceId.APP_STORE, Decimal("0.022"), AT, True), TODAY)
    assert rate_chart(result, Region.UK) == rate_chart(result, Region.UK)
