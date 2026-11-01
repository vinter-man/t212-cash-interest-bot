"""Buttons under a /rate answer: the same question at the rate another source publishes."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from cash_interest.answer import Answer
from cash_interest.board import Row
from cash_interest.money import pct
from cash_interest.sources import SourceId


class RateCb(CallbackData, prefix="r"):
    """Everything needed to answer again, so a button works after a restart: `r:EUR:20000.00:5y:app_store`.
    Telegram does not check callback data against the message it came from, so it is validated
    again on the way back like anything a user types."""

    ccy: str
    amount: str
    period: str
    source: str


def alternatives(result: Answer, row: Row | None) -> InlineKeyboardMarkup | None:
    """One button per rate the other sources give, named after the sources that give it."""
    if row is None:
        return None
    by_rate: dict[str, list[SourceId]] = {}
    for source, quote in row.quotes.items():
        if quote.apy != result.quote.apy:
            by_rate.setdefault(pct(quote.apy), []).append(source)
    buttons = [
        InlineKeyboardButton(
            text=f"{rate} · {', '.join(s.short for s in sources)}",
            callback_data=RateCb(
                ccy=result.ccy, amount=str(result.amount), period=result.period.code, source=sources[0]
            ).pack(),
        )
        for rate, sources in by_rate.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
