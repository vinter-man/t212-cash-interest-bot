"""The picture under a /rate answer, drawn like the rest of the project: ink on paper, a pencil
wobble, one monospaced face.

Three things, top to bottom: what the balance has earned at each milestone, how it grows over
the period, and the first two weeks to the cent, each day as a one-cent cup that fills with the
fraction carried and empties into a payment.

Matplotlib is imported here and nowhere else, with the Agg backend and a bare Figure, so the bot
needs no display and never touches pyplot's global state. Floats appear only as positions on the
page; every number printed comes from the Decimal answer.
"""

from __future__ import annotations

import io
import threading
from importlib import resources
from typing import Any

import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from cash_interest.answer import Answer
from cash_interest.calc import CENT
from cash_interest.money import fraction, money, pct, whole
from cash_interest.sources import Region

PAPER = "#F7F6F2"
INK = "#151515"
GREY = "#6E6D69"
FAINT = "#B9B7B0"
# The pencil: lines wobble a little, the same way on every render (scale, length, randomness).
SKETCH = (1.1, 90.0, 1.6)
CUPS = 14
WIDTH, HEIGHT, DPI = 10.0, 8.6, 160


def _register_fonts() -> str:
    """IBM Plex Mono ships with the package (OFL), so the server draws what a laptop draws."""
    fonts = resources.files("cash_interest").joinpath("fonts")
    for name in ("IBMPlexMono-Regular.ttf", "IBMPlexMono-SemiBold.ttf"):
        with resources.as_file(fonts.joinpath(name)) as path:
            font_manager.fontManager.addfont(str(path))
    return "IBM Plex Mono"


FAMILY = _register_fonts()
# rcParams are global: one chart at a time, so two answers rendering at once cannot mix styles.
_LOCK = threading.Lock()
STYLE: dict[str, Any] = {
    "font.family": FAMILY,
    "font.size": 12,
    "text.color": INK,
    "axes.edgecolor": INK,
    "hatch.color": INK,
    "hatch.linewidth": 0.8,
    # "$10 … $0.0067" is money, not two dollar signs around TeX.
    "text.parse_math": False,
}
# A tick label needs this much of the axis to itself.
LABEL_GAP = 0.1


def _y(inches_from_top: float) -> float:
    return 1 - inches_from_top / HEIGHT


def _axes(fig: Figure, top: float, height: float, left: float = 0.6, right: float = 0.5) -> Axes:
    """An axes box placed in inches from the top-left corner."""
    return fig.add_axes((left / WIDTH, _y(top + height), (WIDTH - left - right) / WIDTH, height / HEIGHT))


def _milestones(fig: Figure, result: Answer) -> None:
    tiles = [(f"after {m.label}", f"+{money(m.paid, result.ccy)}") for m in result.milestones]
    tiles.append((f"balance after {result.period.label}", money(result.sim.balance, result.ccy)))
    step = (WIDTH - 1.1) / len(tiles)
    for n, (label, value) in enumerate(tiles):
        x = (0.6 + n * step) / WIDTH
        fig.text(x, _y(1.55), label, fontsize=11, color=GREY)
        fig.text(x, _y(1.98), value, fontsize=19 if len(tiles) < 4 else 17, fontweight="semibold")


def _growth(fig: Figure, result: Answer) -> None:
    ax = _axes(fig, top=2.45, height=2.9)
    days = result.sim.days
    xs = [0, *(d.n for d in days)]
    ys = [0.0, *(float(d.balance - result.amount) for d in days)]
    top = max(ys[-1], float(CENT))
    ax.fill_between(xs, ys, step="post", facecolor=PAPER, hatch="////", hatchcolor=FAINT, linewidth=0)
    (line,) = ax.step(xs, ys, where="post", color=INK, linewidth=2)
    line.set_sketch_params(*SKETCH)
    (rule,) = ax.plot([0, xs[-1]], [0, 0], color=INK, linewidth=1.4)
    rule.set_sketch_params(*SKETCH)
    marks = [m for m in result.milestones if m.day <= len(days)]
    for m in marks:
        ax.plot([m.day], [float(m.paid)], "o", markersize=8, color=INK, markeredgecolor=PAPER, markeredgewidth=2)
    # "today" anchors the axis; after it the latest milestone wins a collision.
    ticks: list[tuple[int, str]] = []
    for day, label in [(0, "today"), *((m.day, m.label) for m in reversed(marks))]:
        if all(abs(day - other) >= LABEL_GAP * len(days) for other, _ in ticks):
            ticks.append((day, label))
    ax.set_xticks([day for day, _ in ticks], [label for _, label in ticks], fontsize=11)
    ax.tick_params(axis="x", length=0, pad=10, colors=GREY)
    ax.set_yticks([])
    ax.set_xlim(0, xs[-1] * 1.02)
    ax.set_ylim(0, top * 1.12)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_facecolor(PAPER)
    if result.sim.paid == 0:
        when = f"day {result.first_payment:,}" if result.first_payment else "never, at 0%"
        ax.text(0.5, 0.5, f"No payment in this period: the first cent arrives {when}.",
                transform=ax.transAxes, ha="center", va="center", fontsize=12, color=GREY)  # fmt: skip


def _cups(fig: Figure, result: Answer) -> None:
    days = result.sim.days[:CUPS]
    fig.text(0.6 / WIDTH, _y(6.05), f"The first {len(days)} days, to the cent", fontsize=13, fontweight="semibold")
    fig.text(0.6 / WIDTH, _y(6.4), "Each cup is one cent. Whatever does not fill a cent is carried to the next day.",
             fontsize=10.5, color=GREY)  # fmt: skip
    ax = _axes(fig, top=6.6, height=1.3)
    ax.set_xlim(-2.4, CUPS)
    ax.set_ylim(-0.45, 1.65)
    ax.axis("off")
    ax.text(-2.4, 1.32, "paid", fontsize=11, color=GREY, va="center")
    ax.text(-2.4, 0.5, "carried", fontsize=11, color=GREY, va="center")
    ax.text(-2.4, -0.3, "day", fontsize=11, color=GREY, va="center")
    for i, day in enumerate(days):
        x = i + 0.18
        level = float(day.carried / CENT)
        if level > 0:
            ax.add_patch(Rectangle((x, 0), 0.64, level, facecolor=PAPER, edgecolor=INK, hatch="////", linewidth=0))
        (cup,) = ax.plot([x, x, x + 0.64, x + 0.64], [1, 0, 0, 1], color=INK, linewidth=1.3)
        cup.set_sketch_params(*SKETCH)
        paid = f"{day.paid:,.2f}"
        ax.text(x + 0.32, 1.32, paid, ha="center", va="center", fontsize=10 if len(paid) <= 5 else 8.5,
                color=INK if day.paid else FAINT, fontweight="semibold" if day.paid else "normal")  # fmt: skip
        ax.text(x + 0.32, -0.3, str(day.n), ha="center", va="center", fontsize=10, color=GREY)


def rate_chart(result: Answer, region: Region) -> bytes:
    """PNG of one /rate answer."""
    quote = result.quote
    with _LOCK, mpl.rc_context(STYLE):  # type: ignore[arg-type]  # keys checked against a Literal list
        fig = Figure(figsize=(WIDTH, HEIGHT), dpi=DPI)
        fig.patch.set_facecolor(PAPER)
        title = f"{whole(result.amount, result.ccy)} at {pct(quote.apy)} for {result.period.label}"
        fig.text(0.6 / WIDTH, _y(0.62), title, fontsize=19, fontweight="semibold")
        checked = quote.at.strftime("%d %b %Y")
        fig.text(0.6 / WIDTH, _y(0.98), f"{region} view · {quote.source.label}, {checked}"
                 f"{' (stale)' if quote.stale else ''} · paid daily, compounding", fontsize=11, color=GREY)  # fmt: skip
        _milestones(fig, result)
        _growth(fig, result)
        _cups(fig, result)
        sim = result.sim
        footer = (
            f"Rounding down: {fraction(sim.carried, result.ccy)} still carried at the end, "
            f"{fraction(result.missed, result.ccy)} of compounding missed."
        )
        fig.text(0.6 / WIDTH, _y(8.2), footer, fontsize=10.5, color=GREY)
        fig.text(0.6 / WIDTH, _y(8.45), "Before tax. Unofficial, not financial advice.", fontsize=10.5, color=GREY)
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor=PAPER)
    return buffer.getvalue()
