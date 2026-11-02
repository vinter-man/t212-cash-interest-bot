"""Wires the bot together and runs it, with two jobs beside the polling loop:

- `poll`: read every source, every six hours (APScheduler). After a restart the next run is six
  hours after the last one recorded (straight away only if that is already past), so a day of
  deploys does not mean a day of requests.
- `heartbeat`: prove the bot can still reach Telegram, for the container healthcheck.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from cash_interest.bot.handlers import Services, create_router
from cash_interest.config import Settings
from cash_interest.poller import poll
from cash_interest.sources import all_sources, http_client
from cash_interest.store import Store

log = logging.getLogger(__name__)

POLL_HOURS = 6
HEARTBEAT_EVERY = 60

COMMANDS = [
    ("rate", "Interest on a balance: /rate EUR 20000 5y"),
    ("rates", "Every rate from every source"),
    ("diff", "Where the sources disagree"),
    ("help", "How to ask"),
    ("about", "The formula, the sources, tax"),
]
# No trademarks in the name: the bot is about Trading 212, not by it.
NAME = "Cash Interest Buddy (Unofficial)"
SHORT_DESCRIPTION = "Daily interest on uninvested cash, to the cent. Unofficial, not financial advice."
DESCRIPTION = (
    "Works out daily interest on uninvested cash by Trading 212's published formula, and checks "
    "whether their website and app store listings quote the same rates. Unofficial: not "
    "affiliated with Trading 212, and not financial advice."
)


def first_run(last: datetime | None, now: datetime) -> datetime:
    """Six hours after the last poll, or now if that is already past."""
    if last is None:
        return now
    return max(now, last + timedelta(hours=POLL_HOURS))


def build_dispatcher(services: Services) -> Dispatcher:
    dp = Dispatcher()
    dp["services"] = services
    dp.include_router(create_router())
    return dp


async def heartbeat(bot: Bot, path: Path) -> bool:
    """Touch the heartbeat file if Telegram answers; the healthcheck reads its age."""
    try:
        await bot.get_me()
        await asyncio.to_thread(path.write_text, datetime.now(UTC).isoformat())
    except (TelegramAPIError, OSError) as error:
        log.warning("heartbeat failed: %s", type(error).__name__)
        return False
    return True


async def heartbeat_loop(bot: Bot, path: Path) -> None:
    while True:
        await heartbeat(bot, path)
        await asyncio.sleep(HEARTBEAT_EVERY)


async def introduce(bot: Bot) -> None:
    """The command menu and the profile texts, kept in step with the code on every start.

    Each is read first and written only if it differs: Telegram rate-limits these calls (the
    name hardest), and a deploy is a restart. Each is tried on its own, and a failure costs that
    one stale field, never the bot.
    """
    commands = [BotCommand(command=c, description=d) for c, d in COMMANDS]

    async def name() -> None:
        if (await bot.get_my_name()).name != NAME:
            await bot.set_my_name(NAME)

    async def short_description() -> None:
        if (await bot.get_my_short_description()).short_description != SHORT_DESCRIPTION:
            await bot.set_my_short_description(SHORT_DESCRIPTION)

    async def description() -> None:
        if (await bot.get_my_description()).description != DESCRIPTION:
            await bot.set_my_description(DESCRIPTION)

    async def menu() -> None:
        if await bot.get_my_commands() != commands:
            await bot.set_my_commands(commands)

    for update in (menu, name, short_description, description):
        try:
            await update()
        except TelegramAPIError as error:
            log.warning("could not update the bot's %s: %s", update.__name__.replace("_", " "), error)


def make_bot(settings: Settings) -> Bot:
    session = AiohttpSession(api=TelegramAPIServer.from_base(settings.telegram_api)) if settings.telegram_api else None
    return Bot(
        settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


async def run(settings: Settings) -> None:
    log.info("starting %s; region %s; database %s", settings.git_sha[:8], settings.region, settings.db_path)
    store = await Store.open(settings.db_path)
    bot = make_bot(settings)
    services = Services(store, settings.region, owner_id=settings.owner_id, poll_hours=POLL_HOURS)
    dp = build_dispatcher(services)
    scheduler = AsyncIOScheduler(timezone=UTC)
    heart: asyncio.Task[None] | None = None
    try:
        async with http_client() as http:
            sources = all_sources(http, settings.region)

            async def poll_job() -> None:
                await poll(store, sources, services.clock)

            start_at = first_run(await store.last_check(settings.region), services.clock())
            log.info("first poll at %s", start_at.isoformat(timespec="minutes"))
            scheduler.add_job(
                poll_job,
                IntervalTrigger(hours=POLL_HOURS, timezone=UTC),
                next_run_time=start_at,
                id="poll",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            heart = asyncio.create_task(heartbeat_loop(bot, settings.heartbeat_file), name="heartbeat")
            await introduce(bot)
            scheduler.start()
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if heart is not None:
            heart.cancel()
            await asyncio.gather(heart, return_exceptions=True)
        await bot.session.close()
        await store.close()
