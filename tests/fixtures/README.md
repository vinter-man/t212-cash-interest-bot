# Fixtures

Real answers from the four sources, saved on 1 November 2026 — the day the website and the app
stores disagreed — so every parser is tested on what it actually reads.

| File | What it is | How it was saved |
|---|---|---|
| `website/interest-on-cash.html` | trading212.com/interest-on-cash | in a browser (the site challenges other clients), then `scripts/trim_page.py` |
| `website/cards.html` | trading212.com/cards | the same |
| `website/cloudflare-access-denied.html` | what the site sends `curl` and `httpx`: 403, "Access Denied" | `curl`, then `scripts/trim_page.py` |
| `website/cloudflare-challenge.html` | the 403 "Just a moment..." challenge page (it answered `/robots.txt`) | `curl`, unchanged |
| `stores/app-store-{cy,gb,de}.json` | Apple's lookup API for three storefronts; `de` is the German listing, with no English line | `curl`, pretty-printed |
| `stores/google-play-{cy,gb}.html` | the Play listing with `hl=en`, for Cyprus and the UK | `curl`, then `scripts/trim_page.py` |

`trim_page.py` keeps what a parser reads and drops what makes a page megabytes: translations,
reviews and FX tables around the website's rates JSON; styles, fonts, images and SVG (logos
included) in the others. The rates themselves are untouched, and the IP address a block page
echoes back is replaced with a documentation address.

The website pages carry every Trading 212 company's rates at once (`T212CY` for the EU, `AVUSUK`
for the UK, `T212DE`, `T212AU`), so one saved page tests both regions. Broken variants — a
redesign without the JSON, a truncated download, a renamed key, a 25% rate — are made from these
in the tests rather than saved as near-copies.
