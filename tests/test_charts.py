"""The chart is checked for what can be checked without eyes: it renders, the same way every time,
for every shape of answer, and no text lands on other text or off the page. The README
screenshots are where it is looked at."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from itertools import combinations

import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg

from cash_interest.answer import Answer, answer
from cash_interest.board import Quote
from cash_interest.calc import Period
from cash_interest.charts import draw, drawing, rate_chart
from cash_interest.sources import Region, SourceId
from tests.conftest import TODAY

PNG = b"\x89PNG\r\n\x1a\n"
AT = datetime(2026, 11, 1, 20, 30, tzinfo=UTC)


CASES = pytest.mark.parametrize(
    ("ccy", "amount", "apy", "period"),
    [
        ("EUR", "20000", "0.025", Period(5, "y")),  # the README's example
        ("USD", "10", "0.033", Period(30, "d")),  # under a cent a day: the cups fill up
        ("DKK", "1000", "0", Period(1, "y")),  # 0%: a flat line and a note
        ("SEK", "0.10", "0.005", Period(1, "w")),  # the first cent is years away
        ("PLN", "250000", "0.0225", Period(1, "d")),  # a single day, a single cup
        ("EUR", "20000000", "0.025", Period(1, "y")),  # four-digit daily payments in the cups
        ("GBP", "99999999.99", "0.15", Period(10, "y")),  # the widest numbers there can be
    ],
)


def result_for(ccy: str, amount: str, apy: str, period: Period) -> Answer:
    return answer(ccy, Decimal(amount), period, Quote(SourceId.SITE, Decimal(apy), AT, True), TODAY)


@CASES
def test_renders(ccy: str, amount: str, apy: str, period: Period) -> None:
    png = rate_chart(result_for(ccy, amount, apy, period), Region.EU)
    assert png.startswith(PNG)
    assert len(png) > 20_000


@CASES
def test_no_label_overlaps_another_or_leaves_the_page(ccy: str, amount: str, apy: str, period: Period) -> None:
    """Every piece of text is measured as it would be drawn. Mono digits make the widths
    predictable, which is what lets the chart shrink a number that would not fit."""
    with drawing():
        fig = draw(result_for(ccy, amount, apy, period), Region.EU)
        renderer = FigureCanvasAgg(fig).get_renderer()  # type: ignore[no-untyped-call]
        ticks = [t for ax in fig.axes if ax.axison for t in ax.get_xticklabels()]  # an axis off draws none
        texts = [*fig.texts, *(t for ax in fig.axes for t in ax.texts), *ticks]
        boxes = [(t.get_text(), t.get_window_extent(renderer)) for t in texts if t.get_text()]
    for text, box in boxes:
        assert box.x0 >= 0, f"{text!r} runs off the left edge"
        assert box.x1 <= fig.bbox.width, f"{text!r} runs off the right edge"
    for (one, a), (other, b) in combinations(boxes, 2):
        assert not a.shrunk(0.98, 0.98).overlaps(b.shrunk(0.98, 0.98)), f"{one!r} overlaps {other!r}"


def test_one_day_is_one_day() -> None:
    with drawing():
        fig = draw(result_for("PLN", "250000", "0.0225", Period(1, "d")), Region.EU)
    assert "The first day, to the cent" in [t.get_text() for t in fig.texts]


def test_the_same_answer_draws_the_same_picture() -> None:
    """The pencil wobble is seeded, so a chart is reproducible byte for byte."""
    result = answer("EUR", Decimal(500), Period(6, "m"), Quote(SourceId.APP_STORE, Decimal("0.022"), AT, True), TODAY)
    assert rate_chart(result, Region.UK) == rate_chart(result, Region.UK)
