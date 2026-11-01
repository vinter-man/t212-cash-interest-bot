"""The two scripts that feed the repository itself: the screenshot exporter and the fixture trimmer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cash_interest.sources import Region, SourceId
from cash_interest.sources.website import page_rates
from scripts import export_shots, trim_page
from tests.conftest import NOW, fixture

PNG = b"\x89PNG\r\n\x1a\n"
SHOTS = {"rate", "rate_app", "small", "diff", "errors", "rates", "subscribe"}


class TestExportShots:
    async def test_every_shot_is_a_real_reply(self, tmp_path: Path) -> None:
        shots = await export_shots.build(tmp_path)
        assert set(shots) == SHOTS
        for name in ("rate", "rate_app", "small"):
            assert (tmp_path / f"{name}.png").read_bytes().startswith(PNG)
        reply = shots["rate"][1]["in"]
        assert reply["photo"] == "rate.png"
        assert reply["keyboard"] == [["2.2% · iOS, Play"]]
        assert "Balance after 5 years: <b>€22,627.78</b>" in reply["html"]
        assert "Rate: App Store" in shots["rate_app"][1]["in"]["html"]

    async def test_the_table_shows_the_website_as_it_usually_is(self, tmp_path: Path) -> None:
        shots = await export_shots.build(tmp_path)
        table = shots["rates"][1]["in"]["html"]
        assert "EUR   2.50*  2.50*  2.20   2.20 ≠" in table
        assert "HTTP 403, bot check" in table
        assert "iOS: checked 02 Nov 02:30" in table

    async def test_errors_and_alerts(self, tmp_path: Path) -> None:
        shots = await export_shots.build(tmp_path)
        assert [item["out"] for item in shots["errors"] if "out" in item] == [
            "/rate eru 20000",
            "/rate eur 20k banana",
            "/rate eur 20000 11y",
        ]
        assert "Did you mean EUR?" in shots["errors"][1]["in"]["html"]
        alert = shots["subscribe"][2]["in"]["html"]
        assert "▲ App Store: 2.2% → <b>2.5%</b>" in alert

    def test_main_writes_the_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(export_shots, "OUT", tmp_path / "src" / "shots.json")
        monkeypatch.setattr(export_shots, "PUBLIC", tmp_path / "public")
        export_shots.main()
        assert set(json.loads((tmp_path / "src" / "shots.json").read_text())) == SHOTS
        assert (tmp_path / "public" / "small.png").exists()


class TestTrimPage:
    def test_a_trimmed_page_still_parses_the_same(self) -> None:
        page = fixture("website/cards.html").decode()
        trimmed = trim_page.trim_next(page)
        assert len(trimmed) <= len(page)
        before = page_rates(page, SourceId.CARDS, Region.EU, NOW)
        assert page_rates(trimmed, SourceId.CARDS, Region.EU, NOW) == before

    def test_translations_and_reviews_are_dropped(self) -> None:
        page = (
            '<html><head><title>T</title></head><body><script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"_nextI18Next":{"x":1},"trustpilotReviewsData":[],"interestOnCashRates":{}}},'
            '"page":"/cards"}</script></body></html>'
        )
        trimmed = trim_page.trim_next(page)
        assert "_nextI18Next" not in trimmed
        assert "trustpilot" not in trimmed
        assert '"interestOnCashRates":{}' in trimmed
        assert "<title>T</title>" in trimmed

    def test_a_page_without_next_data(self) -> None:
        with pytest.raises(SystemExit, match="no __NEXT_DATA__"):
            trim_page.trim_next("<html></html>")

    def test_other_pages_keep_only_what_is_read(self) -> None:
        page = (
            "<html><head><style>body{color:red}</style></head><body>"
            "<svg><path d='M0 0'/></svg><script>track()</script>"
            "<script src='/cdn-cgi/challenge-platform/scripts/main.js'></script>"
            "<script>var d = 'High interest on your uninvested cash';</script>"
            '<img src="data:image/png;base64,iVBORw0KGgo=">'
            "<p>Your IP: 1.2.3.4</p></body></html>"
        )
        trimmed = trim_page.trim_other(page)
        assert "<style>" not in trimmed
        assert "<svg>" not in trimmed
        assert "track()" not in trimmed
        assert "challenge-platform" in trimmed
        assert "uninvested cash" in trimmed
        assert 'src="data:,"' in trimmed
        assert "Your IP: 203.0.113.7" in trimmed
        assert "1.2.3.4" not in trimmed

    def test_main(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        source, target = tmp_path / "saved.html", tmp_path / "out" / "page.html"
        source.write_bytes(fixture("website/interest-on-cash.html"))
        monkeypatch.setattr(sys, "argv", ["trim_page.py", str(source), str(target)])
        trim_page.main()
        assert "interestOnCashRates" in target.read_text()
        assert "->" in capsys.readouterr().out
