"""What every source says right now, as a Markdown table: one request per source, like the bot.

    uv run python scripts/check_rates.py [--region EU|UK]

The "Check rates now" workflow writes this to its job summary, and the nightly live check puts
it in the issue it opens when a parser breaks. Nothing is stored.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from datetime import datetime

from cash_interest.board import SourceState, rows
from cash_interest.money import pct
from cash_interest.sources import ORDER, FetchError, Region, SourceId, all_sources, http_client, utcnow


async def snapshot(region: Region) -> tuple[dict[SourceId, SourceState], dict[SourceId, str]]:
    """Every source once: its rates, or why there are none."""
    states: dict[SourceId, SourceState] = {}
    problems: dict[SourceId, str] = {}
    async with http_client() as client:
        for source in all_sources(client, region):
            at = utcnow()
            try:
                found = await source.fetch()
            except FetchError as error:
                problems[source.id] = f"{type(error).__name__}: {error}"
                states[source.id] = SourceState(source.id, checked_at=at, failing_since=at, problem=str(error))
                continue
            states[source.id] = SourceState(
                source.id, {r.ccy: r.apy for r in found}, ok_at=at, via="http", checked_at=at
            )
    return states, problems


def markdown(
    states: Mapping[SourceId, SourceState], problems: Mapping[SourceId, str], region: Region, at: datetime
) -> str:
    lines = [
        f"### Interest on cash, {region} view ({region.company})",
        "",
        "| CCY | " + " | ".join(s.label for s in ORDER) + " | |",
        "|---|" + "---:|" * len(ORDER) + "---|",
    ]
    for row in rows(states):
        cells = [pct(row.quotes[s].apy) if s in row.quotes else "—" for s in ORDER]
        lines.append(f"| {row.ccy} | " + " | ".join(cells) + f" | {'≠' if row.diverges else ''} |")
    lines += ["", "| Source | Result |", "|---|---|"]
    for source in ORDER:
        count = len(states[source].rates)
        lines.append(f"| {source.label} | {problems.get(source) or f'{count} rates'} |")
    lines += ["", f"Checked {at:%Y-%m-%d %H:%M} UTC. ≠ marks a currency the sources disagree on."]
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", type=Region, choices=list(Region), default=Region.EU)
    args = parser.parse_args()
    at = utcnow()
    states, problems = await snapshot(args.region)
    print(markdown(states, problems, args.region, at))


if __name__ == "__main__":
    asyncio.run(main())
