"""A Bot API server small enough to read: the methods the bot calls, answered in memory.

The bot under test is the real program (`python -m cash_interest`) pointed at this server with
TELEGRAM_API, so everything between the operating system and Telegram's API — settings, the
database, the scheduler, aiogram's HTTP session, multipart uploads — runs for real.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

BOT = {"id": 42, "is_bot": True, "first_name": "Cash Interest", "username": "t212_cash_interest_bot"}
# Answers that do not depend on the request: who the bot is, and a profile with nothing set yet.
FIXED: dict[str, Any] = {
    "getMe": BOT,
    "getMyCommands": [],
    "getMyName": {"name": ""},
    "getMyShortDescription": {"short_description": ""},
    "getMyDescription": {"description": ""},
}


@dataclass
class Call:
    method: str
    params: dict[str, Any]
    files: dict[str, bytes] = field(default_factory=dict)

    def upload(self, name: str) -> bytes:
        """A file the call uploaded: aiogram sends `photo=attach://<part>` and the bytes as <part>."""
        return self.files[str(self.params[name]).removeprefix("attach://")]


class FakeTelegram:
    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.updates: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.called = asyncio.Condition()
        self._ids = itertools.count(1)
        self._messages = itertools.count(100)
        self.app = web.Application()
        self.app.router.add_route("*", "/bot{token}/{method}", self.handle)
        self.runner = web.AppRunner(self.app)
        self.port = 0

    async def start(self) -> str:
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        return f"http://127.0.0.1:{self.port}"

    async def stop(self) -> None:
        await self.runner.cleanup()

    def push_text(self, text: str, user_id: int = 5150) -> None:
        self.updates.put_nowait({"update_id": next(self._ids), "message": self._message(user_id, text=text)})

    def push_callback(self, data: str, user_id: int = 5150) -> None:
        origin = self._message(user_id, photo=True, caption="…")
        query = {"id": str(next(self._ids)), "from": self._user(user_id), "chat_instance": "c", "data": data,
                 "message": origin}  # fmt: skip
        self.updates.put_nowait({"update_id": next(self._ids), "callback_query": query})

    async def wait_for(self, method: str, count: int = 1, within: float = 30) -> list[Call]:
        """The calls of `method` once there are at least `count` of them."""
        deadline = time.monotonic() + within
        async with self.called:
            while len(found := [c for c in self.calls if c.method == method]) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"{count} × {method} expected, got {len(found)}: {self.methods()}")
                try:
                    await asyncio.wait_for(self.called.wait(), remaining)
                except TimeoutError:
                    continue
            return found

    def methods(self) -> list[str]:
        return [c.method for c in self.calls]

    @staticmethod
    def _user(user_id: int) -> dict[str, Any]:
        return {"id": user_id, "is_bot": False, "first_name": "Test"}

    def _message(self, chat_id: int, *, text: str | None = None, photo: bool = False,
                 caption: str | None = None) -> dict[str, Any]:  # fmt: skip
        message: dict[str, Any] = {
            "message_id": next(self._messages),
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": self._user(chat_id),
        }
        if text is not None:
            message["text"] = text
        if photo:
            message["photo"] = [{"file_id": "p", "file_unique_id": "p", "width": 1600, "height": 1376}]
            message["caption"] = caption or ""
        return message

    async def handle(self, request: web.Request) -> web.Response:
        method = request.match_info["method"]
        params: dict[str, Any] = {}
        files: dict[str, bytes] = {}
        form = await request.post()
        for key, value in form.items():
            if isinstance(value, web.FileField):
                files[key] = value.file.read()
            else:
                params[key] = value
        if method == "getUpdates":
            result: Any = await self._get_updates(float(params.get("timeout", 0)))
        else:
            result = self._answer(method, params)
        async with self.called:
            self.calls.append(Call(method, params, files))
            self.called.notify_all()
        return web.json_response({"ok": True, "result": result})

    async def _get_updates(self, long_poll: float) -> list[dict[str, Any]]:
        """Waits for an update like Telegram does, but a second at most, so the test stays quick."""
        try:
            first = await asyncio.wait_for(self.updates.get(), min(long_poll, 1.0))
        except TimeoutError:
            return []
        batch = [first]
        while not self.updates.empty():
            batch.append(self.updates.get_nowait())
        return batch

    def _answer(self, method: str, params: dict[str, Any]) -> Any:
        if method in FIXED:
            return FIXED[method]
        chat_id = int(params.get("chat_id", 0) or 0)
        match method:
            case "sendMessage":
                return self._message(chat_id, text=params["text"])
            case "sendPhoto":
                return self._message(chat_id, photo=True, caption=params.get("caption"))
            case "editMessageMedia":
                media = json.loads(params["media"])
                return self._message(chat_id or 5150, photo=True, caption=media.get("caption"))
            case _:
                return True
