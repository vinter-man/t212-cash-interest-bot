"""The bot's profile picture: one of the chart's one-cent cups, filling up. No logos.

    uv run python scripts/avatar.py            # writes docs/assets/avatar.png
    uv run python scripts/avatar.py --upload   # and makes it the bot's photo (BOT_TOKEN from .env)

Telegram crops profile pictures to a circle, so everything sits well inside it.
"""

from __future__ import annotations

import argparse
import asyncio
import io
from pathlib import Path
from typing import Any

import matplotlib as mpl
from aiogram import Bot
from aiogram.types import BufferedInputFile, InputProfilePhotoStatic
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from cash_interest.charts import INK, PAPER, SKETCH, STYLE
from cash_interest.config import Settings

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "avatar.png"


def draw() -> bytes:
    style: dict[str, Any] = {**STYLE, "hatch.linewidth": 2.2}  # thicker strokes for a small picture
    with mpl.rc_context(style):  # type: ignore[arg-type]  # keys checked against a Literal list
        fig = Figure(figsize=(4, 4), dpi=160)
        fig.patch.set_facecolor(PAPER)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.add_patch(Rectangle((0.34, 0.22), 0.32, 0.27, facecolor=PAPER, edgecolor=INK, hatch="///", linewidth=0))
        (cup,) = ax.plot([0.34, 0.34, 0.66, 0.66], [0.68, 0.22, 0.22, 0.68], color=INK, linewidth=5)
        cup.set_sketch_params(*SKETCH)
        ax.text(0.5, 0.79, "1¢", ha="center", va="center", fontsize=40, fontweight="semibold", color=INK)
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor=PAPER)
    return buffer.getvalue()


async def upload(png: bytes) -> None:
    async with Bot(Settings().bot_token.get_secret_value()) as bot:
        await bot.set_my_profile_photo(InputProfilePhotoStatic(photo=BufferedInputFile(png, "avatar.png")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upload", action="store_true", help="set it as the bot's profile photo")
    args = parser.parse_args()
    png = draw()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(png)
    print(f"wrote {OUT}")
    if args.upload:
        asyncio.run(upload(png))
        print("uploaded")


if __name__ == "__main__":
    main()
