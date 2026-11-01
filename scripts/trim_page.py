"""Shrinks a saved page into a test fixture without touching what the parsers read.

    uv run python scripts/trim_page.py saved.html tests/fixtures/website/cards.html

A trading212.com page keeps its `__NEXT_DATA__` JSON, minus the translations, reviews and FX
tables that make up most of it; the rates object inside keeps every value. Any other page loses
its inline styles, fonts, images, SVG (logos included) and every script but the ones a parser or
the bot-check detection looks at. What is left is small enough to review, and the IP address a
block page echoes back becomes a documentation address (RFC 5737).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# pageProps a parser or a person reading the fixture might want; the rest is copy and reviews.
KEEP = ("interestOnCashRates", "geolocationCookie", "currenciesWithChangingRates", "warningType")
NEXT_DATA = re.compile(r'(<script[^>]*\bid="__NEXT_DATA__"[^>]*>)(.*?)(</script>)', re.S)
TITLE = re.compile(r"<title[^>]*>.*?</title>", re.S)
NOISE = re.compile(r"<style[^>]*>.*?</style>|<svg.*?</svg>|<noscript>.*?</noscript>", re.S)
SCRIPT = re.compile(r"<script[^>]*>.*?</script>", re.S)
INLINE_DATA = re.compile(r"data:[a-z]+/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+")
YOUR_IP = re.compile(r"(Your IP:\s*)[0-9a-fA-F:.]+")
# Scripts worth keeping: the Play listing's description data, Cloudflare's challenge loader.
WANTED = ("uninvested cash", "challenge-platform")


def trim_next(page: str) -> str:
    match = NEXT_DATA.search(page)
    if match is None:
        raise SystemExit("no __NEXT_DATA__ in this page")
    data = json.loads(match.group(2))
    props = data["props"]["pageProps"]
    data["props"]["pageProps"] = {key: props[key] for key in KEEP if key in props}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    title = TITLE.search(page)
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f"{title.group(0) if title else ''}</head><body>\n"
        "<!-- Trimmed by scripts/trim_page.py: markup, translations and reviews removed. -->\n"
        f'<div id="__next"></div>\n{match.group(1)}{blob}{match.group(3)}\n</body></html>\n'
    )


def trim_other(page: str) -> str:
    page = NOISE.sub("", page)
    page = SCRIPT.sub(lambda m: m.group(0) if any(w in m.group(0) for w in WANTED) else "", page)
    page = YOUR_IP.sub(r"\g<1>203.0.113.7", page)
    return INLINE_DATA.sub("data:,", page)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    page = args.source.read_text(encoding="utf-8")
    trimmed = trim_next(page) if "__NEXT_DATA__" in page else trim_other(page)
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(trimmed, encoding="utf-8")
    print(f"{args.source} ({len(page):,} chars) -> {args.target} ({len(trimmed):,} chars)")


if __name__ == "__main__":
    main()
