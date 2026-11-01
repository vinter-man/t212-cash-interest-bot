"""The whole program, started the way Docker starts it, talking to a fake Telegram.

The database is seeded with the saved pages and stamped "just checked", so the first poll is six
hours away and the test never touches the network. Then: commands in, replies out, a button
pressed, and a clean exit on SIGTERM — what `docker stop` sends.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cash_interest.bot import keyboards as kb
from cash_interest.sources import Region, SourceId
from cash_interest.sources.stores import AppStore, GooglePlay
from cash_interest.sources.website import page_rates
from cash_interest.store import Store
from tests.conftest import fixture
from tests.e2e.fake_telegram import Call, FakeTelegram

pytestmark = pytest.mark.e2e
PNG = b"\x89PNG\r\n\x1a\n"


async def seed(path: Path) -> None:
    now = datetime.now(UTC)
    async with await Store.open(path) as store:
        for source, name in [(SourceId.SITE, "interest-on-cash.html"), (SourceId.CARDS, "cards.html")]:
            found = page_rates(fixture(f"website/{name}").decode(), source, Region.EU, now)
            await store.record(source, Region.EU, found, at=now)
        apple, google = AppStore(None, Region.EU), GooglePlay(None, Region.EU)  # type: ignore[arg-type]
        await store.record(SourceId.APP_STORE, Region.EU, apple.parse(fixture("stores/app-store-cy.json"), now), at=now)
        play = google.parse(fixture("stores/google-play-cy.html"), now)
        await store.record(SourceId.GOOGLE_PLAY, Region.EU, play, at=now)


@pytest.fixture
async def telegram() -> AsyncIterator[FakeTelegram]:
    server = FakeTelegram()
    await server.start()
    yield server
    await server.stop()


async def test_the_program(telegram: FakeTelegram, tmp_path: Path) -> None:
    db = tmp_path / "data" / "bot.db"
    await seed(db)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", str(tmp_path)),  # matplotlib's font cache lives there
        "BOT_TOKEN": "42:TEST",
        "TELEGRAM_API": f"http://127.0.0.1:{telegram.port}",
        "DB_PATH": str(db),
        "HEARTBEAT_FILE": str(tmp_path / "heartbeat"),
        "OWNER_ID": "1",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "cash_interest",
        cwd=tmp_path, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )  # fmt: skip

    async def reply(method: str, count: int = 1) -> list[Call]:
        """Waits for the bot's calls, but not on a bot that has already died."""
        calls = asyncio.ensure_future(telegram.wait_for(method, count))
        exited = asyncio.ensure_future(process.wait())
        await asyncio.wait({calls, exited}, return_when=asyncio.FIRST_COMPLETED)
        if not calls.done():
            calls.cancel()
            output = (await process.stdout.read()).decode() if process.stdout else ""
            pytest.fail(f"the bot exited with {process.returncode} while waiting for {method}:\n{output}")
        exited.cancel()
        return calls.result()

    try:
        await reply("getUpdates")
        commands = (await reply("setMyCommands"))[0]
        assert '"command":"rate"' in commands.params["commands"].replace(" ", "")

        telegram.push_text("/start")
        (start,) = await reply("sendMessage")
        assert "not affiliated with Trading 212" in start.params["text"]

        telegram.push_text("/rate EUR 20000 5y")
        (photo,) = await reply("sendPhoto")
        assert photo.upload("photo").startswith(PNG)
        assert "Balance after 5 years: <b>€22,627.78</b>" in photo.params["caption"]
        assert "App Store and Google Play say 2.2%" in photo.params["caption"]

        telegram.push_text("/rates")
        rates = (await reply("sendMessage", 2))[-1]
        assert "EUR   2.50   2.50   2.20   2.20 ≠" in rates.params["text"]

        telegram.push_callback(kb.RateCb(ccy="EUR", amount="20000.00", period="5y", source="app_store").pack())
        (edit,) = await reply("editMessageMedia")
        media = json.loads(edit.params["media"])
        assert "EUR 2.2% · 5 years" in media["caption"]
        assert edit.files[media["media"].removeprefix("attach://")].startswith(PNG)

        telegram.push_text("/subscribe eur")
        subscribed = (await reply("sendMessage", 3))[-1]
        assert "Subscribed to EUR" in subscribed.params["text"]
        async with await Store.open(db) as store:
            assert await store.subscribers("EUR") == [5150]

        assert (tmp_path / "heartbeat").exists()
    finally:
        if process.returncode is None:
            process.send_signal(signal.SIGTERM)
        output = (await asyncio.wait_for(process.communicate(), 30))[0].decode()
    assert process.returncode == 0, output
    assert "Traceback" not in output, output
    assert "first poll at" in output
