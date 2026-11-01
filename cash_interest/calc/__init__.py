"""Pure arithmetic: no I/O, no clock, no Telegram. Everything here is covered to 100%."""

from cash_interest.calc.interest import (
    CENT,
    MAX_DAYS,
    Day,
    Simulation,
    daily_interest,
    daily_rate,
    first_payment_day,
    simulate,
    to_cent,
)
from cash_interest.calc.period import MONTH, YEAR, Period, add_months

__all__ = [
    "CENT",
    "MAX_DAYS",
    "MONTH",
    "YEAR",
    "Day",
    "Period",
    "Simulation",
    "add_months",
    "daily_interest",
    "daily_rate",
    "first_payment_day",
    "simulate",
    "to_cent",
]
