from __future__ import annotations

from datetime import date

import pytest

from cash_interest.calc import MAX_DAYS, MONTH, YEAR, Period, add_months


@pytest.mark.parametrize(
    ("start", "months", "end"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 11, 2), 2, date(2027, 1, 2)),
        (date(2026, 12, 15), 1, date(2027, 1, 15)),
        (date(2028, 2, 29), 12, date(2029, 2, 28)),
        (date(2026, 5, 31), 120, date(2036, 5, 31)),
    ],
)
def test_add_months(start: date, months: int, end: date) -> None:
    assert add_months(start, months) == end


@pytest.mark.parametrize(
    ("period", "start", "days"),
    [
        (Period(30, "d"), date(2026, 11, 2), 30),
        (Period(2, "w"), date(2026, 11, 2), 14),
        (Period(6, "m"), date(2026, 11, 2), 181),
        (YEAR, date(2026, 11, 2), 365),
        (YEAR, date(2027, 11, 2), 366),
        (Period(5, "y"), date(2026, 11, 2), 1826),
        (Period(10, "y"), date(2026, 11, 2), 3653),
        (MONTH, date(2027, 2, 1), 28),
    ],
)
def test_days(period: Period, start: date, days: int) -> None:
    assert period.days(start) == days


def test_ten_years_always_fit_a_simulation() -> None:
    longest = max(Period(10, "y").days(date(2026 + y, 1, 1)) for y in range(4))
    assert longest <= MAX_DAYS


@pytest.mark.parametrize(("count", "unit"), [(0, "d"), (11, "y"), (121, "m"), (522, "w"), (MAX_DAYS + 1, "d")])
def test_out_of_range(count: int, unit: str) -> None:
    with pytest.raises(ValueError, match="outside"):
        Period(count, unit)  # type: ignore[arg-type]


def test_names() -> None:
    assert (Period(5, "y").code, Period(5, "y").label) == ("5y", "5 years")
    assert (MONTH.code, MONTH.label) == ("1m", "1 month")
    assert Period(2, "w").label == "2 weeks"
