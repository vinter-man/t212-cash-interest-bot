"""Reply texts that the dispatcher tests do not reach: edge cases of the caption and the status lines."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from cash_interest.answer import answer
from cash_interest.board import Quote, SourceState, rows
from cash_interest.bot import keyboards as kb
from cash_interest.bot import replies
from cash_interest.calc import Period
from cash_interest.sources import Region, SourceId
from cash_interest.store import Change
from tests.conftest import NOW, SITE_EU, STORE_EU, TODAY, state

LATER = NOW + timedelta(hours=6)


def quote(apy: str, source: SourceId = SourceId.SITE, *, stale: bool = False) -> Quote:
    return Quote(source, Decimal(apy), NOW, stale)


class TestSourceLine:
    def test_never_checked(self) -> None:
        assert replies.source_line(SourceState(SourceId.SITE)) == "site: not checked yet"

    def test_never_succeeded(self) -> None:
        line = replies.source_line(state(SourceId.CARDS, {}, failing_since=NOW, problem="HTTP 403, bot check"))
        assert line == "cards: no value since 01 Nov 20:30 (HTTP 403, bot check)"

    def test_stale_after_a_live_read(self) -> None:
        line = replies.source_line(state(SourceId.APP_STORE, STORE_EU, failing_since=LATER, problem="HTTP 502"))
        assert line == "iOS: stale since 02 Nov 02:30 (HTTP 502); value from the last good check, 01 Nov 20:30"

    def test_a_saved_page_is_not_a_check(self) -> None:
        line = replies.source_line(state(SourceId.SITE, SITE_EU, via="upload"))
        assert line == "site: saved page sent 01 Nov 20:30"

    def test_diff_says_where_a_value_came_from(self) -> None:
        later = NOW + timedelta(hours=6)
        states = {
            SourceId.SITE: state(SourceId.SITE, SITE_EU, via="upload"),
            SourceId.CARDS: state(
                SourceId.CARDS, SITE_EU, failing_since=later, problem="HTTP 403, bot check", via="upload"
            ),
            SourceId.APP_STORE: state(SourceId.APP_STORE, STORE_EU, failing_since=later, problem="HTTP 502"),
        }
        text = replies.diff(states, Region.EU)
        assert "2.5% · trading212.com/interest-on-cash · saved page sent 01 Nov 20:30 UTC" in text
        assert "HTTP 403, bot check; this value is from a saved page sent 01 Nov 20:30 UTC" in text
        assert "HTTP 502; this value is from a check at 01 Nov 20:30 UTC" in text

    def test_problems_are_escaped(self) -> None:
        line = replies.source_line(state(SourceId.SITE, {}, failing_since=NOW, problem="<script>"))
        assert "&lt;script&gt;" in line


class TestCaption:
    def test_zero_rate(self) -> None:
        result = answer("DKK", Decimal(1000), Period(1, "y"), quote("0"), TODAY)
        caption = replies.rate_caption(result, None)
        assert "At 0% nothing is ever paid." in caption
        assert "Balance after 1 year: <b>DKK 1,000.00</b>" in caption

    def test_saved_page_and_stale_are_both_said(self) -> None:
        stale = Quote(SourceId.SITE, Decimal("0.025"), NOW, True, "upload")
        caption = replies.rate_caption(answer("EUR", Decimal(100), Period(1, "y"), stale, TODAY), None)
        assert "Rate: trading212.com/interest-on-cash, a saved page sent 01 Nov 2026 <i>(stale)</i>" in caption

    def test_several_other_values(self) -> None:
        states = {
            SourceId.SITE: state(SourceId.SITE, {"EUR": "0.025"}),
            SourceId.APP_STORE: state(SourceId.APP_STORE, {"EUR": "0.022"}),
            SourceId.GOOGLE_PLAY: state(SourceId.GOOGLE_PLAY, {"EUR": "0.021"}),
        }
        row = rows(states)[0]
        result = answer("EUR", Decimal(100), Period(1, "y"), quote("0.025"), TODAY)
        assert "App Store says 2.2%; Google Play says 2.1%" in replies.rate_caption(result, row)
        assert [b.text for b in kb.alternatives(result, row).inline_keyboard[0]] == ["2.2% · iOS", "2.1% · Play"]  # type: ignore[union-attr]

    def test_no_buttons_when_everyone_agrees(self) -> None:
        states = {SourceId.SITE: state(SourceId.SITE, SITE_EU), SourceId.CARDS: state(SourceId.CARDS, SITE_EU)}
        result = answer("EUR", Decimal(100), Period(1, "y"), quote("0.025"), TODAY)
        assert kb.alternatives(result, rows(states)[0]) is None
        assert kb.alternatives(result, None) is None

    def test_the_longest_caption_fits_telegram(self) -> None:
        """Telegram refuses a photo caption over 1,024 characters, and the bot has no fallback for
        one: this is the longest caption there can be (the widest amount, four different rates,
        a saved and stale source), and it has to fit."""
        states = {s: state(s, {"EUR": f"0.0{i + 1}"}) for i, s in enumerate(SourceId)}
        widest = Quote(SourceId.CARDS, Decimal("0.0275"), NOW, True, "upload")
        result = answer("EUR", Decimal("99999999.99"), Period(10, "y"), widest, TODAY)
        assert len(replies.rate_caption(result, rows(states)[0])) <= 1024


def test_change_alert() -> None:
    changes = [
        Change(SourceId.APP_STORE, Region.EU, "EUR", Decimal("0.022"), Decimal("0.025"), NOW),
        Change(SourceId.GOOGLE_PLAY, Region.EU, "EUR", Decimal("0.022"), Decimal("0.02"), NOW),
    ]
    states = {
        SourceId.SITE: state(SourceId.SITE, SITE_EU),
        SourceId.CARDS: SourceState(SourceId.CARDS),
        SourceId.APP_STORE: state(SourceId.APP_STORE, {"EUR": "0.025"}),
        SourceId.GOOGLE_PLAY: state(SourceId.GOOGLE_PLAY, {"EUR": "0.02"}),
    }
    text = replies.change_alert(changes, states)
    assert text.startswith("<b>EUR rate changed</b> (EU view)")
    assert "▲ App Store: 2.2% → <b>2.5%</b>" in text
    assert "▼ Google Play: 2.2% → <b>2%</b>" in text
    assert "Now: 2.5% on trading212.com/interest-on-cash and App Store; 2% on Google Play." in text
    assert "<code>/rate EUR 10000</code> · <code>/unsubscribe EUR</code>" in text


def test_the_two_website_pages_are_one_website() -> None:
    site, cards, app_store = SourceId.SITE, SourceId.CARDS, SourceId.APP_STORE
    assert replies.says([site, cards]) == "the website says"
    assert replies.says([app_store, SourceId.GOOGLE_PLAY]) == "App Store and Google Play say"
    assert replies.says([site, cards, app_store]) == "the website and App Store say"
    assert replies.says([cards]) == "trading212.com/cards says"


def test_an_alert_marks_what_is_stale() -> None:
    change = Change(SourceId.APP_STORE, Region.EU, "EUR", Decimal("0.022"), Decimal("0.025"), LATER)
    blocked = {"failing_since": LATER, "problem": "HTTP 403, bot check", "via": "upload"}
    states = {
        SourceId.SITE: state(SourceId.SITE, SITE_EU, **blocked),  # type: ignore[arg-type]
        SourceId.CARDS: state(SourceId.CARDS, SITE_EU, **blocked),  # type: ignore[arg-type]
        SourceId.APP_STORE: state(SourceId.APP_STORE, {"EUR": "0.025"}, at=LATER),
        SourceId.GOOGLE_PLAY: state(SourceId.GOOGLE_PLAY, STORE_EU, at=LATER),
    }
    text = replies.change_alert([change], states)
    assert "Now: 2.5% on the website (stale) and App Store; 2.2% on Google Play." in text


def test_a_warning_starts_with_a_capital() -> None:
    states = {s: state(s, SITE_EU if s in (SourceId.SITE, SourceId.CARDS) else STORE_EU) for s in SourceId}
    app = Quote(SourceId.APP_STORE, Decimal("0.022"), NOW, False)
    row = next(r for r in rows(states) if r.ccy == "EUR")
    caption = replies.rate_caption(answer("EUR", Decimal(100), Period(1, "y"), app, TODAY), row)
    assert "⚠️ The website says 2.5%." in caption


def test_tax_is_said_per_company() -> None:
    eu, uk = replies.about(Region.EU, 6), replies.about(Region.UK, 6)
    assert "17% withholding tax and 2.65% GHS" in eu
    assert "17%" not in uk
    assert "ISA" in uk
    assert replies.TAX_ARTICLE in eu
    assert replies.TAX_ARTICLE in uk


def test_subscribing_with_no_rate_yet() -> None:
    assert replies.subscribed("CHF", True, None).startswith("Subscribed to CHF: I will write")


def test_upload_reply_lists_the_changes() -> None:
    change = Change(SourceId.SITE, Region.EU, "EUR", Decimal("0.025"), Decimal("0.0275"), NOW)
    text = replies.upload_done(SourceId.SITE, 10, [change])
    assert "Different from before:\nEUR: 2.5% → 2.75%" in text


def test_help_names_the_region() -> None:
    assert "UK view" in replies.help_text(Region.UK)
    assert "Trading 212 UK Ltd, FCA" in replies.start(Region.UK)
    assert "every 6 hours" in replies.about(Region.EU, 6)
