"""Telegram handlers. They parse, look up, delegate the arithmetic and the drawing, and reply."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from cash_interest import charts
from cash_interest.answer import answer
from cash_interest.board import pick, rows
from cash_interest.bot import keyboards as kb
from cash_interest.bot import replies
from cash_interest.bot.parsing import EXAMPLE, InputError, Query, parse_currency, parse_query
from cash_interest.sources import FetchError, Region, SourceId, utcnow
from cash_interest.sources.website import page_rates, page_source
from cash_interest.store import Store

log = logging.getLogger(__name__)

# A saved page is under 1.5 MB; anything far bigger is not one.
MAX_UPLOAD = 5 * 1024 * 1024


@dataclass(slots=True)
class Services:
    store: Store
    region: Region
    clock: Callable[[], datetime] = utcnow
    owner_id: int | None = None
    poll_hours: int = 6


@dataclass(frozen=True, slots=True)
class Reply:
    caption: str
    chart: bytes | None
    keyboard: InlineKeyboardMarkup | None


async def known_currencies(services: Services) -> set[str]:
    states = await services.store.states(services.region)
    return {ccy for state in states.values() for ccy in state.rates}


async def build_reply(services: Services, query: Query, prefer: SourceId | None = None) -> Reply:
    states = await services.store.states(services.region)
    quote = pick(states, query.ccy, prefer)
    if quote is None:
        return Reply(replies.no_rate(query.ccy, services.region, states), None, None)
    result = answer(query.ccy, query.amount, query.period, quote, services.clock().date())
    row = next((r for r in rows(states) if r.ccy == query.ccy), None)
    try:
        chart: bytes | None = await asyncio.to_thread(charts.rate_chart, result, services.region)
    except Exception:  # the picture is a bonus; the numbers must still arrive
        log.exception("chart failed")
        chart = None
    return Reply(replies.rate_caption(result, row), chart, kb.alternatives(result, row))


async def send_reply(message: Message, reply: Reply) -> None:
    """The chart with the text as its caption; the text alone if the chart could not be drawn."""
    if reply.chart is None:
        await message.answer(reply.caption, reply_markup=reply.keyboard)
        return
    photo = BufferedInputFile(reply.chart, "interest.png")
    await message.answer_photo(photo, caption=reply.caption, reply_markup=reply.keyboard)


def input_error(error: InputError, example: str = EXAMPLE) -> str:
    return f"{escape(str(error))}\nFor example: <code>{example}</code>"


async def on_start(message: Message, services: Services) -> None:
    await message.answer(replies.start(services.region))


async def on_help(message: Message, services: Services) -> None:
    await message.answer(replies.help_text(services.region))


async def on_about(message: Message, services: Services) -> None:
    await message.answer(replies.about(services.region, services.poll_hours))


async def rate(message: Message, services: Services, text: str) -> None:
    try:
        query = parse_query(text, await known_currencies(services))
    except InputError as error:
        await message.answer(input_error(error))
        return
    await send_reply(message, await build_reply(services, query))


async def on_rate(message: Message, command: CommandObject, services: Services) -> None:
    if not command.args:
        await message.answer(f"Currency and amount, and a period if you like:\n<code>{EXAMPLE}</code>")
        return
    await rate(message, services, command.args)


async def on_rates(message: Message, services: Services) -> None:
    states = await services.store.states(services.region)
    await message.answer(replies.rates_table(states, services.region))


async def on_diff(message: Message, services: Services) -> None:
    states = await services.store.states(services.region)
    await message.answer(replies.diff(states, services.region))


async def on_subscribe(message: Message, command: CommandObject, services: Services) -> None:
    store = services.store
    if not command.args:
        await message.answer(replies.subscriptions(await store.subscriptions(message.chat.id)))
        return
    try:
        ccy = parse_currency(command.args, await known_currencies(services))
    except InputError as error:
        await message.answer(input_error(error, "/subscribe EUR"))
        return
    new = await store.subscribe(message.chat.id, ccy, at=services.clock())
    quote = pick(await store.states(services.region), ccy)
    await message.answer(replies.subscribed(ccy, new, quote))


async def on_unsubscribe(message: Message, command: CommandObject, services: Services) -> None:
    store = services.store
    if not command.args:
        await message.answer(replies.subscriptions(await store.subscriptions(message.chat.id)))
        return
    try:
        ccy = parse_currency(command.args, await known_currencies(services))
    except InputError as error:
        await message.answer(input_error(error, "/unsubscribe EUR"))
        return
    await message.answer(replies.unsubscribed(ccy, await store.unsubscribe(message.chat.id, ccy)))


async def on_rate_button(callback: CallbackQuery, callback_data: kb.RateCb, services: Services) -> None:
    try:
        query = parse_query(
            f"{callback_data.ccy} {callback_data.amount} {callback_data.period}",
            await known_currencies(services),
        )
        source = SourceId(callback_data.source)
    except (InputError, ValueError):
        await callback.answer("This button is out of date. Ask again with /rate.", show_alert=True)
        return
    message = callback.message
    reply = await build_reply(services, query, prefer=source)
    await callback.answer()
    if message is None or isinstance(message, InaccessibleMessage):
        return
    try:
        if reply.chart is not None and message.photo:
            media = InputMediaPhoto(media=BufferedInputFile(reply.chart, "interest.png"), caption=reply.caption)
            await message.edit_media(media, reply_markup=reply.keyboard)
        else:
            await send_reply(message, reply)
    except TelegramBadRequest as error:  # "message is not modified" on a second tap
        log.info("rate button: %s", error.message)


async def on_document(message: Message, services: Services, bot: Bot) -> None:
    user = message.from_user
    if services.owner_id is None or user is None or user.id != services.owner_id:
        await message.answer("I only read text. /help shows what to ask.")
        return
    document = message.document
    if document is None or document.file_size is None or document.file_size > MAX_UPLOAD:
        await message.answer(replies.upload_failed("the file is larger than a saved page can be, or of no stated size"))
        return
    buffer = io.BytesIO()
    await bot.download(document, destination=buffer)
    html = buffer.getvalue().decode("utf-8", errors="replace")
    at = services.clock()
    try:
        source = page_source(html)
        rates = page_rates(html, source, services.region, at)
    except FetchError as error:
        await message.answer(replies.upload_failed(str(error)))
        return
    # Recorded, but no alert goes out: a saved page carries no date, so only the owner, who knows
    # when they saved it, hears what differs. Subscribers hear from the live checks.
    changes = await services.store.record(source, services.region, rates, at=at, via="upload")
    await message.answer(replies.upload_done(source, len(rates), changes))


async def on_text(message: Message, services: Services) -> None:
    await rate(message, services, message.text or "")


async def on_anything_else(message: Message) -> None:
    await message.answer(f"Try <code>{EXAMPLE}</code>, or /help.")


def create_router() -> Router:
    """A fresh router each time: aiogram attaches a router to one dispatcher only."""
    router = Router(name="cash-interest")
    router.message.register(on_start, CommandStart())
    router.message.register(on_help, Command("help"))
    router.message.register(on_about, Command("about"))
    router.message.register(on_rate, Command("rate"))
    router.message.register(on_rates, Command("rates"))
    router.message.register(on_diff, Command("diff"))
    router.message.register(on_subscribe, Command("subscribe"))
    router.message.register(on_unsubscribe, Command("unsubscribe"))
    # Plain text and files are for the bot only in a private chat; in a group they are just talk.
    private = F.chat.type == "private"
    router.message.register(on_document, private, F.document)
    router.message.register(on_text, private, F.text & ~F.text.startswith("/"))
    router.message.register(on_anything_else, private)
    router.callback_query.register(on_rate_button, kb.RateCb.filter())
    return router
