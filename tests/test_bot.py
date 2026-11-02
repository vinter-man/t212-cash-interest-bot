"""End to end through the real dispatcher: updates in, Bot API calls out, nothing on the network.

`FakeSession` stands in for aiogram's HTTP session. It records every API method the handlers call
and answers with plausible objects, so the whole path — filters, callback data, parsing, the
calculation, the chart, the database — runs as it does in production.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageMedia,
    GetFile,
    GetMe,
    GetMyCommands,
    GetMyDescription,
    GetMyName,
    GetMyShortDescription,
    SendMessage,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import (
    BotDescription,
    BotName,
    BotShortDescription,
    BufferedInputFile,
    CallbackQuery,
    Chat,
    Document,
    File,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    Sticker,
    Update,
    User,
)

from cash_interest.bot import keyboards as kb
from cash_interest.bot.app import build_dispatcher
from cash_interest.bot.handlers import Services
from cash_interest.sources import Region, SourceId
from cash_interest.store import Status, Store
from tests.conftest import NOW, SITE_EU, STORE_EU, fixture, rates

USER_ID = 5150
OWNER_ID = 1
PNG = b"\x89PNG\r\n\x1a\n"


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.files: dict[str, bytes] = {}
        # What getMyCommands, getMyName, … answer; empty means "nothing set yet".
        self.profile: dict[str, Any] = {}
        self._ids = itertools.count(1000)
        # Set to make the next call of that method type fail, as Telegram sometimes does.
        self.fail_with: dict[type, Exception] = {}

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:  # noqa: ASYNC109 - aiogram's signature
        self.calls.append(method)
        if (error := self.fail_with.pop(type(method), None)) is not None:
            raise error
        answer = self._answers.get(type(method))
        return answer(method) if answer else True

    @property
    def _answers(self) -> dict[type, Callable[[Any], Any]]:
        """What Telegram would return, per method; anything else answers True."""
        profile = self.profile
        return {
            GetMe: lambda _: User(id=42, is_bot=True, first_name="Cash Interest", username="t212_cash_interest_bot"),
            GetMyCommands: lambda _: profile.get("commands", []),
            GetMyName: lambda _: BotName(name=profile.get("name", "")),
            GetMyShortDescription: lambda _: BotShortDescription(
                short_description=profile.get("short_description", "")
            ),
            GetMyDescription: lambda _: BotDescription(description=profile.get("description", "")),
            GetFile: lambda m: File(file_id=m.file_id, file_unique_id="u", file_path=f"documents/{m.file_id}"),
            SendMessage: lambda m: Message(
                message_id=next(self._ids), date=datetime.now(UTC), chat=Chat(id=USER_ID, type="private"), text=m.text
            ),
            SendPhoto: lambda _: photo_message(next(self._ids)),
            EditMessageMedia: lambda _: photo_message(next(self._ids)),
        }

    async def close(self) -> None:
        pass

    async def stream_content(self, url: str, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield self.files[url.rsplit("/", 1)[-1]]

    def sent(self) -> list[SendMessage | SendPhoto | EditMessageMedia]:
        return [c for c in self.calls if isinstance(c, SendMessage | SendPhoto | EditMessageMedia)]

    def texts(self) -> list[str]:
        out = []
        for call in self.sent():
            if isinstance(call, SendMessage):
                out.append(call.text)
            elif isinstance(call, SendPhoto):
                out.append(call.caption or "")
            else:
                out.append(call.media.caption or "")
        return out

    def last(self) -> str:
        return self.texts()[-1]


def photo_message(message_id: int, caption: str = "…") -> Message:
    photo = [PhotoSize(file_id="f", file_unique_id="u", width=1600, height=1376)]
    return Message(message_id=message_id, date=datetime.now(UTC), chat=Chat(id=USER_ID, type="private"),
                   photo=photo, caption=caption)  # fmt: skip


def photo_bytes(call: SendPhoto | EditMessageMedia) -> bytes:
    photo = call.photo if isinstance(call, SendPhoto) else call.media.media
    assert isinstance(photo, BufferedInputFile)
    return photo.data


@dataclass
class Env:
    bot: Bot
    dp: Dispatcher
    session: FakeSession
    services: Services

    async def say(self, text: str, user: User | None = None) -> None:
        await self.dp.feed_update(self.bot, message(text=text, user=user or USER))

    async def send(self, update: Update) -> None:
        await self.dp.feed_update(self.bot, update)


@pytest.fixture
def env(store: Store) -> Env:
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode="HTML"))
    services = Services(store, Region.EU, clock=lambda: NOW, owner_id=OWNER_ID)
    return Env(bot, build_dispatcher(services), session, services)


@pytest.fixture
async def seeded(env: Env) -> Env:
    """The four sources as they stood on 1 November 2026."""
    store = env.services.store
    for source, values in [
        (SourceId.SITE, SITE_EU),
        (SourceId.CARDS, SITE_EU),
        (SourceId.APP_STORE, STORE_EU),
        (SourceId.GOOGLE_PLAY, STORE_EU),
    ]:
        await store.record(source, Region.EU, rates(source, values), at=NOW)
    return env


_ids: Iterator[int] = itertools.count(1)
USER = User(id=USER_ID, is_bot=False, first_name="Test", language_code="en")
OWNER = User(id=OWNER_ID, is_bot=False, first_name="Owner")


def message(text: str | None = None, user: User = USER, **extra: Any) -> Update:
    return Update(
        update_id=next(_ids),
        message=Message(message_id=next(_ids), date=datetime.now(UTC), chat=Chat(id=user.id, type="private"),
                        from_user=user, text=text, **extra),
    )  # fmt: skip


def callback(data: str, *, on_photo: bool = True) -> Update:
    origin = photo_message(77) if on_photo else Message(message_id=77, date=datetime.now(UTC),
                                                         chat=Chat(id=USER_ID, type="private"), text="…")  # fmt: skip
    return Update(update_id=next(_ids), callback_query=CallbackQuery(
        id=str(next(_ids)), from_user=USER, chat_instance="c", data=data, message=origin))  # fmt: skip


def buttons(markup: InlineKeyboardMarkup | None) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row] if markup else []


class TestHelp:
    @pytest.mark.parametrize("command", ["/start", "/help", "/about"])
    async def test_every_help_text_carries_the_disclaimer(self, env: Env, command: str) -> None:
        await env.say(command)
        assert "not affiliated with Trading 212" in env.session.last()
        assert "not financial advice" in env.session.last()

    async def test_about_explains_tax_and_formula(self, env: Env) -> None:
        await env.say("/about")
        text = env.session.last()
        assert "17%" in text
        assert "2.65% GHS" in text
        assert "365.25" in text


class TestRate:
    async def test_answer_is_a_chart_with_the_numbers_in_the_caption(self, seeded: Env) -> None:
        await seeded.say("/rate EUR 20000 5y")
        (call,) = seeded.session.sent()
        assert isinstance(call, SendPhoto)
        assert photo_bytes(call).startswith(PNG)
        caption = call.caption or ""
        assert "€20,000 · EUR 2.5% · 5 years" in caption
        assert "trading212.com/interest-on-cash, 01 Nov 2026" in caption
        assert "Day 1: €1.35 paid" in caption
        assert "1 month: +€40.60 · 1 year: +€499.65 · 5 years: +€2,627.78" in caption
        assert "Balance after 5 years: <b>€22,627.78</b>" in caption
        assert "App Store and Google Play say 2.2%" in caption
        assert buttons(call.reply_markup) == ["2.2% · iOS, Play"]  # type: ignore[arg-type]

    async def test_plain_text_is_a_question_too(self, seeded: Env) -> None:
        await seeded.say("gbp 20k 6m")
        assert "£20,000 · GBP 3.55% · 6 months" in seeded.session.last()

    async def test_small_balances_wait_for_their_first_cent(self, seeded: Env) -> None:
        await seeded.say("/rate USD 10 30d")
        assert "under a cent: the first payment arrives on day 11" in seeded.session.last()

    async def test_a_currency_only_the_website_quotes(self, seeded: Env) -> None:
        await seeded.say("/rate PLN 5000")
        caption = seeded.session.last()
        assert "PLN 2.25%" in caption
        assert "⚠️" not in caption

    async def test_no_source_quotes_it(self, seeded: Env) -> None:
        await seeded.say("/rate CHF 1000")
        assert "No source publishes a CHF rate for the EU view" in seeded.session.last()
        assert "Rates exist for CZK, EUR, GBP, PLN, USD" in seeded.session.last()

    async def test_nothing_fetched_yet(self, env: Env) -> None:
        await env.say("/rate EUR 1000")
        assert "No source has answered yet" in env.session.last()

    async def test_a_stale_website_still_answers_and_says_so(self, seeded: Env) -> None:
        store = seeded.services.store
        await store.record_failure(SourceId.SITE, Region.EU, Status.BLOCKED, "HTTP 403, bot check", at=NOW)
        await store.record_failure(SourceId.CARDS, Region.EU, Status.BLOCKED, "HTTP 403, bot check", at=NOW)
        await seeded.say("/rate PLN 5000")
        assert "<i>(stale)</i>" in seeded.session.last()

    @pytest.mark.parametrize(
        ("text", "error"),
        [
            ("/rate", "Currency and amount"),
            ("/rate eur", "How much?"),
            ("/rate eru 100", "Did you mean EUR?"),
            ("/rate eur 100 <b>", "I do not understand “&lt;b&gt;”"),
        ],
    )
    async def test_errors_come_with_an_example(self, seeded: Env, text: str, error: str) -> None:
        await seeded.say(text)
        assert error in seeded.session.last()
        assert "/rate EUR 20000 5y" in seeded.session.last()

    async def test_when_the_chart_fails_the_numbers_still_arrive(
        self, seeded: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*args: object) -> bytes:
            raise RuntimeError("no fonts today")

        monkeypatch.setattr("cash_interest.bot.handlers.charts.rate_chart", broken)
        await seeded.say("/rate EUR 20000")
        (call,) = seeded.session.sent()
        assert isinstance(call, SendMessage)
        assert "Balance after 1 year" in call.text


class TestOtherSourcesButton:
    async def test_recalculates_at_the_other_rate(self, seeded: Env) -> None:
        data = kb.RateCb(ccy="EUR", amount="20000.00", period="5y", source="app_store").pack()
        await seeded.send(callback(data))
        edit = next(c for c in seeded.session.calls if isinstance(c, EditMessageMedia))
        assert "EUR 2.2% · 5 years" in (edit.media.caption or "")
        assert "Rate: App Store, 01 Nov 2026" in (edit.media.caption or "")
        assert buttons(edit.reply_markup) == ["2.5% · site, cards"]
        assert any(isinstance(c, AnswerCallbackQuery) and not c.show_alert for c in seeded.session.calls)

    @pytest.mark.parametrize(
        "data",
        [
            "r:EUR:20000.00:5y:nowhere",
            "r:XXX:20000.00:5y:site",
            "r:EUR:-5:5y:site",
            "r:EUR:20000.00:99y:site",
        ],
    )
    async def test_forged_or_stale_buttons_get_an_alert(self, seeded: Env, data: str) -> None:
        await seeded.send(callback(data))
        (answer,) = [c for c in seeded.session.calls if isinstance(c, AnswerCallbackQuery)]
        assert answer.show_alert
        assert not seeded.session.sent()

    async def test_a_three_digit_period_survives_the_round_trip(self, seeded: Env) -> None:
        await seeded.say("/rate EUR 20k 365d")
        (photo,) = seeded.session.sent()
        assert isinstance(photo, SendPhoto)
        markup = photo.reply_markup
        assert isinstance(markup, InlineKeyboardMarkup)
        data = markup.inline_keyboard[0][0].callback_data
        assert data == "r:EUR:20000.00:365d:app_store"
        await seeded.send(callback(data))
        edit = next(c for c in seeded.session.calls if isinstance(c, EditMessageMedia))
        assert "EUR 2.2% · 365 days" in (edit.media.caption or "")

    async def test_a_second_tap_on_the_same_button(self, seeded: Env) -> None:
        seeded.session.fail_with[EditMessageMedia] = TelegramBadRequest(GetMe(), "message is not modified")
        await seeded.send(callback(kb.RateCb(ccy="EUR", amount="100.00", period="1y", source="site").pack()))
        assert any(isinstance(c, AnswerCallbackQuery) for c in seeded.session.calls)

    async def test_a_button_under_a_text_answer_sends_a_new_message(self, seeded: Env) -> None:
        data = kb.RateCb(ccy="EUR", amount="100.00", period="1y", source="google_play").pack()
        await seeded.send(callback(data, on_photo=False))
        assert isinstance(seeded.session.sent()[-1], SendPhoto)


class TestTables:
    async def test_rates(self, seeded: Env) -> None:
        await seeded.say("/rates")
        text = seeded.session.last()
        assert "<pre>" in text
        assert "CCY   site  cards    iOS   Play" in text
        assert "EUR   2.50   2.50   2.20   2.20 ≠" in text
        assert "PLN   2.25   2.25      —      — </pre>" in text
        assert "Disagreements: EUR, GBP, USD." in text
        assert "iOS: checked 01 Nov 20:30" in text
        assert "Times are UTC." in text

    async def test_diff(self, seeded: Env) -> None:
        await seeded.say("/diff")
        text = seeded.session.last()
        assert "<b>EUR</b>" in text
        assert "PLN" not in text
        assert "2.2% · App Store · checked 01 Nov 20:30 UTC" in text

    async def test_nothing_to_compare_yet(self, env: Env) -> None:
        await env.say("/rates")
        assert "No source has answered yet" in env.session.last()
        await env.say("/diff")
        assert "No source has answered yet, so there is nothing to compare" in env.session.last()

    async def test_one_source_is_not_an_agreement(self, env: Env) -> None:
        store = env.services.store
        await store.record(SourceId.APP_STORE, Region.EU, rates(SourceId.APP_STORE, STORE_EU), at=NOW)
        await env.say("/diff")
        assert env.session.last() == "Only App Store has answered so far, so there is nothing to compare yet."

    async def test_sources_that_agree(self, env: Env) -> None:
        store = env.services.store
        for source in (SourceId.APP_STORE, SourceId.GOOGLE_PLAY):
            await store.record(source, Region.EU, rates(source, STORE_EU), at=NOW)
        await env.say("/diff")
        assert env.session.last().startswith("No disagreement in the EU view")


class TestSavedPages:
    """The owner forwards a page saved in a browser, when the site will not talk to the bot."""

    def document(self, name: str, size: int | None = None) -> dict[str, Any]:
        return {"document": Document(file_id=name, file_unique_id=name, file_name=name, file_size=size)}

    async def test_owner_upload_is_recorded(self, env: Env) -> None:
        env.session.files["interest-on-cash.html"] = fixture("website/interest-on-cash.html")
        await env.send(message(user=OWNER, **self.document("interest-on-cash.html", 2_000)))
        assert env.session.last() == "Recorded 10 rates from trading212.com/interest-on-cash. Nothing changed."
        state = await env.services.store.state(SourceId.SITE, Region.EU)
        assert state.via == "upload"

    async def test_an_upload_tells_the_owner_what_differs(self, seeded: Env) -> None:
        page = fixture("website/cards.html").replace(b'"T212CY":{"CZK":0.03', b'"T212CY":{"CZK":0.028')
        seeded.session.files["cards.html"] = page
        await seeded.send(message(user=OWNER, **self.document("cards.html", 2_000)))
        assert seeded.session.last().endswith("Different from before:\nCZK: 3% → 2.8%")

    async def test_not_a_saved_page(self, env: Env) -> None:
        env.session.files["notes.html"] = b"<html>shopping list</html>"
        await env.send(message(user=OWNER, **self.document("notes.html", 30)))
        assert "I could not read that page: this is not a saved trading212.com" in env.session.last()

    @pytest.mark.parametrize("size", [50 * 1024 * 1024, None])
    async def test_too_big_or_of_unknown_size(self, env: Env, size: int | None) -> None:
        await env.send(message(user=OWNER, **self.document("huge.html", size)))
        assert "larger than a saved page can be, or of no stated size" in env.session.last()
        assert not any(isinstance(c, GetFile) for c in env.session.calls)

    async def test_only_the_owner(self, env: Env) -> None:
        await env.send(message(user=USER, **self.document("interest-on-cash.html", 2_000)))
        assert "I only read text" in env.session.last()
        assert not any(isinstance(c, GetFile) for c in env.session.calls)


async def test_plain_text_in_a_group_is_not_a_question(seeded: Env) -> None:
    group = Update(update_id=next(_ids), message=Message(message_id=next(_ids), date=datetime.now(UTC),
                   chat=Chat(id=-100, type="supergroup"), from_user=USER, text="nice bot"))  # fmt: skip
    await seeded.send(group)
    assert not seeded.session.sent()


async def test_a_file_in_a_group_is_not_for_the_bot(env: Env) -> None:
    document = Document(file_id="f", file_unique_id="f", file_name="cards.html", file_size=2_000)
    group = Update(update_id=next(_ids), message=Message(message_id=next(_ids), date=datetime.now(UTC),
                   chat=Chat(id=-100, type="supergroup"), from_user=OWNER, document=document))  # fmt: skip
    await env.send(group)
    assert not env.session.calls


async def test_a_sticker_gets_a_hint(env: Env) -> None:
    sticker = Sticker(file_id="s", file_unique_id="s", type="regular", width=1, height=1, is_animated=False,
                      is_video=False)  # fmt: skip
    await env.send(message(sticker=sticker))
    assert "Try <code>/rate EUR 20000 5y</code>" in env.session.last()


async def test_an_unknown_command_gets_a_hint(env: Env) -> None:
    await env.say("/start@t212_cash_interest_bot")
    await env.say("/nonsense")
    assert "/help" in env.session.last()
