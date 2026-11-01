"""The wiring around the handlers: scheduling, alerts to subscribers, the heartbeat."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import GetMe, SendMessage, SetMyCommands, SetMyDescription, SetMyName, SetMyShortDescription
from aiogram.types import BotCommand
from pydantic import SecretStr

from cash_interest.bot import app
from cash_interest.bot.handlers import Services
from cash_interest.config import Settings
from cash_interest.poller import Notify
from cash_interest.sources import Region, SourceId
from cash_interest.store import Change, Store
from tests.conftest import NOW, rates
from tests.test_bot import FakeSession


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(session: FakeSession) -> Bot:
    return Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode="HTML"))


def test_first_run() -> None:
    assert app.first_run(None, NOW) == NOW
    assert app.first_run(NOW - timedelta(hours=1), NOW) == NOW + timedelta(hours=5)
    assert app.first_run(NOW - timedelta(days=2), NOW) == NOW


class TestNotifier:
    @pytest.fixture
    async def services(self, store: Store) -> Services:
        app_store = SourceId.APP_STORE
        await store.record(app_store, Region.EU, rates(app_store, {"EUR": "0.025"}), at=NOW)
        for chat in (1, 2, 3):
            await store.subscribe(chat, "EUR", at=NOW)
        await store.subscribe(4, "GBP", at=NOW)
        return Services(store, Region.EU)

    CHANGE = Change(SourceId.APP_STORE, Region.EU, "EUR", Decimal("0.022"), Decimal("0.025"), NOW)

    @staticmethod
    def notifier(bot: Bot, services: Services, waits: list[float] | None = None) -> Notify:
        async def sleep(seconds: float) -> None:
            if waits is not None:
                waits.append(seconds)

        return app.make_notifier(bot, services, sleep)

    async def test_each_subscriber_of_the_currency_gets_one_message(
        self, bot: Bot, session: FakeSession, services: Services
    ) -> None:
        await self.notifier(bot, services)([self.CHANGE])
        sent = [c for c in session.calls if isinstance(c, SendMessage)]
        assert [c.chat_id for c in sent] == [1, 2, 3]
        assert "App Store: 2.2% → <b>2.5%</b>" in sent[0].text

    async def test_a_chat_that_blocked_the_bot_is_forgotten(
        self, bot: Bot, session: FakeSession, services: Services
    ) -> None:
        session.fail_with[SendMessage] = TelegramForbiddenError(GetMe(), "bot was blocked by the user")
        await self.notifier(bot, services)([self.CHANGE])
        assert await services.store.subscribers("EUR") == [2, 3]

    async def test_flood_control_waits_and_retries(self, bot: Bot, session: FakeSession, services: Services) -> None:
        waits: list[float] = []
        session.fail_with[SendMessage] = TelegramRetryAfter(GetMe(), "Too Many Requests", retry_after=3)
        await self.notifier(bot, services, waits)([self.CHANGE])
        assert waits[0] == 3
        assert waits[1:] == [app.SEND_GAP] * 3
        assert [c.chat_id for c in session.calls if isinstance(c, SendMessage)] == [1, 1, 2, 3]

    async def test_one_failure_does_not_stop_the_rest(self, bot: Bot, session: FakeSession, services: Services) -> None:
        session.fail_with[SendMessage] = TelegramNetworkError(GetMe(), "timeout")
        await self.notifier(bot, services)([self.CHANGE])
        assert len([c for c in session.calls if isinstance(c, SendMessage)]) == 3
        assert await services.store.subscribers("EUR") == [1, 2, 3]


async def test_heartbeat(bot: Bot, session: FakeSession, tmp_path: Path) -> None:
    beat = tmp_path / "heartbeat"
    assert await app.heartbeat(bot, beat)
    assert beat.exists()
    session.fail_with[GetMe] = TelegramNetworkError(GetMe(), "down")
    assert not await app.heartbeat(bot, tmp_path / "other")
    assert not (tmp_path / "other").exists()


async def test_introduce_sets_commands_and_profile(bot: Bot, session: FakeSession) -> None:
    await app.introduce(bot)
    (commands,) = [c for c in session.calls if isinstance(c, SetMyCommands)]
    assert [c.command for c in commands.commands] == [
        "rate",
        "rates",
        "diff",
        "subscribe",
        "unsubscribe",
        "help",
        "about",
    ]
    (name,) = [c for c in session.calls if isinstance(c, SetMyName)]
    assert "212" not in (name.name or "")
    (long,) = [c for c in session.calls if isinstance(c, SetMyDescription)]
    (short,) = [c for c in session.calls if isinstance(c, SetMyShortDescription)]
    assert "not affiliated with Trading 212" in (long.description or "")
    assert "Unofficial" in (short.short_description or "")


async def test_introduce_writes_only_what_differs(bot: Bot, session: FakeSession) -> None:
    """Telegram rate-limits profile changes; a restart that changes nothing must not spend them."""
    session.profile = {
        "commands": [BotCommand(command=c, description=d) for c, d in app.COMMANDS],
        "name": app.NAME,
        "short_description": app.SHORT_DESCRIPTION,
        "description": app.DESCRIPTION,
    }
    await app.introduce(bot)
    assert not [c for c in session.calls if type(c).__name__.startswith("SetMy")]


async def test_one_field_that_cannot_be_updated_does_not_hold_back_the_rest(bot: Bot, session: FakeSession) -> None:
    session.fail_with[SetMyName] = TelegramRetryAfter(GetMe(), "Too Many Requests", retry_after=86400)
    await app.introduce(bot)  # logs a warning, raises nothing
    assert [c for c in session.calls if isinstance(c, SetMyDescription | SetMyShortDescription)]


def test_make_bot_uses_a_custom_api_server() -> None:
    local = Settings(bot_token=SecretStr("42:TEST"), telegram_api="http://127.0.0.1:8081")
    bot = app.make_bot(local)
    assert bot.session.api.base == "http://127.0.0.1:8081/bot{token}/{method}"
    default = app.make_bot(Settings(bot_token=SecretStr("42:TEST")))
    assert default.session.api.base.startswith("https://api.telegram.org")


def test_settings_ignore_other_projects_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "42:TEST")
    monkeypatch.setenv("SERVER_PASSWORD", "not ours")
    monkeypatch.setenv("OWNER_ID", "")
    monkeypatch.setenv("REGION", "UK")
    monkeypatch.setenv("LOG_LEVEL", "info")
    settings = Settings(_env_file=None)
    assert (settings.region, settings.owner_id, settings.log_level) == (Region.UK, None, "INFO")
