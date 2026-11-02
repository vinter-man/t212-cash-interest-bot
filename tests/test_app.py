"""The wiring around the handlers: scheduling, the heartbeat, the bot's profile."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import GetMe, SetMyCommands, SetMyDescription, SetMyName, SetMyShortDescription
from aiogram.types import BotCommand
from pydantic import SecretStr

from cash_interest.bot import app
from cash_interest.config import Settings
from cash_interest.sources import Region
from tests.conftest import NOW
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
