"""Every message the bot sends, as Telegram HTML. Anything a user typed is escaped on the way in.

Telegram HTML rather than MarkdownV2: only `<`, `>` and `&` need escaping, and nobody has to
escape a full stop in `€1,234.56`.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from html import escape

from cash_interest.answer import Answer
from cash_interest.board import Quote, Row, SourceState, others, rows
from cash_interest.money import fraction, money, pct, pct2, whole
from cash_interest.sources import ORDER, Region, SourceId
from cash_interest.store import Change

REPO = "https://github.com/vinter-man/t212-cash-interest-bot"
FORMULA = (
    "https://helpcentre.trading212.com/hc/en-us/articles/40012428081949-How-is-interest-on-my-cash-calculated-and-paid"
)
TAX_ARTICLE = "https://helpcentre.trading212.com/hc/en-us/articles/15472255836957-Do-I-have-to-pay-taxes-on-the-earned-interest-on-cash"
# What the help centre's tax article says for each company; the bot itself calculates no tax.
TAX = {
    Region.EU: "Tax residents of Cyprus pay a 17% withholding tax and 2.65% GHS on the interest; "
    "everyone else is paid gross, and their own country may tax it.",
    Region.UK: "No tax on ISA interest; otherwise it depends on where you are tax resident, and "
    "nothing is calculated here.",
}
DISCLAIMER = "Unofficial: not affiliated with Trading 212, and not financial advice."


def when(at: datetime) -> str:
    return at.strftime("%d %b %H:%M")


def day(at: datetime) -> str:
    return at.strftime("%d %b %Y")


def provenance(quote: Quote) -> str:
    """Where a rate came from and when: `App Store, 01 Nov 2026`. A saved page's date is the day
    the owner sent it, which is all the bot knows about it."""
    if quote.via == "upload":
        return f"{quote.source.label}, a saved page sent {day(quote.at)}"
    return f"{quote.source.label}, {day(quote.at)}"


def source_line(state: SourceState) -> str:
    """One source's health, named as in the /rates header: when it was last asked, how that went."""
    name = state.source.short
    if state.checked_at is None:
        return f"{name}: not checked yet"
    if state.failing_since is None:
        return f"{name}: checked {when(state.checked_at)}"
    problem = escape(state.problem or "failed")
    if not state.rates:
        return f"{name}: no value since {when(state.failing_since)} ({problem})"
    via = "a saved page" if state.via == "upload" else "the last good check"
    read = f"; value from {via}, {when(state.ok_at)}" if state.ok_at else ""
    return f"{name}: stale since {when(state.failing_since)} ({problem}){read}"


def names(sources: Sequence[SourceId], stale: Collection[SourceId] = ()) -> str:
    """Sources in prose; both website pages together are just "the website". Those in `stale`
    say so."""

    def label(name: str, *of: SourceId) -> str:
        return f"{name} (stale)" if all(s in stale for s in of) else name

    website = [s for s in sources if s in (SourceId.SITE, SourceId.CARDS)]
    parts = [label(s.label, s) for s in sources if s not in website]
    if len(website) == 2:
        parts.insert(0, label("the website", *website))
    elif website:
        parts.insert(0, label(website[0].label, website[0]))
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def says(sources: Sequence[SourceId]) -> str:
    plural = len(sources) > 1 and set(sources) != {SourceId.SITE, SourceId.CARDS}
    return f"{names(sources)} {'say' if plural else 'says'}"


# --- /rate ---------------------------------------------------------------------------------


def rate_caption(result: Answer, row: Row | None) -> str:
    """The text under the chart: its figures again, all but the day-by-day cups, so the answer
    can be read without the picture."""
    q, ccy, sim = result.quote, result.ccy, result.sim
    first = sim.days[0]
    lines = [
        f"<b>{whole(result.amount, ccy)} · {ccy} {pct(q.apy)} · {result.period.label}</b>",
        f"Rate: {provenance(q)}{' <i>(stale)</i>' if q.stale else ''}",
        "",
    ]
    if result.under_a_cent:
        lines.append(
            f"A day earns {fraction(result.first_day_interest, ccy)}, under a cent: "
            f"the first payment arrives on day {result.first_payment:,}."
        )
    elif result.first_payment is None:
        lines.append("At 0% nothing is ever paid.")
    else:
        lines.append(f"Day 1: {money(first.paid, ccy)} paid, {fraction(first.carried, ccy)} carried to day 2.")
    lines.append(" · ".join(f"{m.label}: +{money(m.paid, ccy)}" for m in result.milestones))
    lines.append(f"Balance after {result.period.label}: <b>{money(sim.balance, ccy)}</b>")
    lines += [
        "",
        f"Rounding down: {fraction(sim.carried, ccy)} still carried (paid once it makes a cent); "
        f"{fraction(result.missed, ccy)} of compounding missed meanwhile.",
    ]
    if row is not None and (differ := others(row, q)):
        said = "; ".join(f"{says(sources)} {pct(apy)}" for apy, sources in differ.items())
        lines.append(f"⚠️ {said[0].upper()}{said[1:]}. Tap below to recalculate.")
    lines += ["", f"<i>Before tax. {DISCLAIMER}</i> /about"]
    return "\n".join(lines)


def no_rate(ccy: str, region: Region, states: Mapping[SourceId, SourceState]) -> str:
    known = sorted({c for state in states.values() for c in state.rates})
    listed = f" Rates exist for {', '.join(known)}." if known else " No source has answered yet; try again later."
    return f"No source publishes a {escape(ccy)} rate for the {region} view.{listed}"


# --- /rates and /diff ------------------------------------------------------------------------


def _cell(row: Row, source: SourceId) -> str:
    """Six characters: the rate right-aligned in five, then `*` if it is stale."""
    quote = row.quotes.get(source)
    if quote is None:
        return f"{'—':>5} "
    return f"{pct2(quote.apy):>5}{'*' if quote.stale else ' '}"


def rates_table(states: Mapping[SourceId, SourceState], region: Region) -> str:
    table = rows(states)
    head = f"<b>Interest on cash · {region} view</b>, {region.company}"
    footer = "Times are UTC.\n" + "\n".join(source_line(states[s]) for s in ORDER if s in states)
    if not table:
        return f"{head}\n\nNo source has answered yet.\n\n<i>{footer}</i>"
    lines = ["CCY " + "".join(f" {s.short:>5} " for s in ORDER)]
    lines += [
        f"{row.ccy} " + "".join(f" {_cell(row, s)}" for s in ORDER) + ("≠" if row.diverges else "") for row in table
    ]
    stale = any(quote.stale for row in table for quote in row.quotes.values())
    notes = [f"% a year (AER/APY). ≠ sources disagree{', * stale' if stale else ''}."]
    if diverging := [r.ccy for r in table if r.diverges]:
        notes.append(f"Disagreements: {', '.join(diverging)}. /diff has the details.")
    return f"{head}\n<pre>{'\n'.join(lines)}</pre>\n" + "\n".join(notes) + f"\n\n<i>{footer}</i>"


def _checked(state: SourceState) -> str:
    """When a source was last asked and, if that failed, why and how old its value is."""
    if state.checked_at is None:
        return "not checked yet"
    text = f"checked {when(state.checked_at)} UTC"
    if state.failing_since is not None and state.ok_at is not None:
        text += f" ({escape(state.problem or 'failed')}; this value is from {when(state.ok_at)} UTC)"
    return text


def diff(states: Mapping[SourceId, SourceState], region: Region) -> str:
    answered = [source for source in ORDER if source in states and states[source].rates]
    if not answered:
        return "No source has answered yet, so there is nothing to compare. /rates shows the checks."
    if len(answered) == 1:
        return f"Only {answered[0].label} has answered so far, so there is nothing to compare yet."
    diverging = [row for row in rows(states) if row.diverges]
    if not diverging:
        return (
            f"No disagreement in the {region} view: every currency that more than one source quotes "
            "has the same rate in each. /rates shows the table."
        )
    blocks = [f"<b>Where the sources disagree · {region} view</b>"]
    for row in diverging:
        lines = [f"<b>{row.ccy}</b>"]
        lines += [f"{pct(q.apy)} · {source.label} · {_checked(states[source])}" for source, q in row.quotes.items()]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# --- alerts and subscriptions ----------------------------------------------------------------


def change_alert(changes: Sequence[Change], states: Mapping[SourceId, SourceState]) -> str:
    """One message for one currency's changes in a poll, with what every source says now."""
    ccy = changes[0].ccy
    lines = [f"<b>{ccy} rate changed</b> ({changes[0].region} view)"]
    for change in changes:
        arrow = "▲" if change.new > change.old else "▼"
        lines.append(f"{arrow} {change.source.label}: {pct(change.old)} → <b>{pct(change.new)}</b>")
    by_rate: dict[Decimal, list[SourceId]] = {}
    for source in ORDER:
        if ccy in states[source].rates:
            by_rate.setdefault(states[source].rates[ccy], []).append(source)
    stale = {source for source, state in states.items() if state.stale}
    now = "; ".join(f"{pct(apy)} on {names(sources, stale)}" for apy, sources in by_rate.items())
    lines += ["", f"Now: {now}.", f"<code>/rate {ccy} 10000</code> · <code>/unsubscribe {ccy}</code>"]
    return "\n".join(lines)


def subscribed(ccy: str, new: bool, quote: Quote | None) -> str:
    current = f" Now: {pct(quote.apy)} ({provenance(quote)})." if quote else ""
    if not new:
        return f"You are already subscribed to {ccy}.{current}"
    return (
        f"Subscribed to {ccy}: I will write when any source changes its {ccy} rate.{current}\n"
        f"<code>/unsubscribe {ccy}</code> to stop."
    )


def unsubscribed(ccy: str, had: bool) -> str:
    return f"Unsubscribed from {ccy}." if had else f"You were not subscribed to {ccy}."


def subscriptions(currencies: Sequence[str]) -> str:
    if not currencies:
        return "No subscriptions. <code>/subscribe EUR</code> to get a message when the EUR rate changes."
    return f"Subscribed to: {', '.join(currencies)}.\n<code>/unsubscribe EUR</code> to stop one."


# --- help ------------------------------------------------------------------------------------


def start(region: Region) -> str:
    return (
        "<b>Interest on uninvested cash, to the cent</b>\n\n"
        "I work out what Trading 212's published daily-interest formula pays on a cash balance, "
        "and I check whether their website and app store listings quote the same rates.\n\n"
        "<code>/rate EUR 20000 5y</code> — interest, day by day\n"
        "<code>/rates</code> — every rate from every source\n"
        "<code>/diff</code> — only where the sources disagree\n"
        "<code>/subscribe EUR</code> — a message when the rate changes\n\n"
        f"{region} view ({region.company}). <i>{DISCLAIMER}</i> /about"
    )


def help_text(region: Region) -> str:
    return (
        "<b>/rate</b> currency, amount, and a period if you like (a year by default):\n"
        "<code>/rate EUR 20000 5y</code>  <code>/rate gbp 20k 6m</code>  <code>/rate €1,500.50 30d</code>\n"
        "Periods from <code>1d</code> to <code>10y</code>: <code>30d</code>, <code>2w</code>, "
        "<code>6m</code>, <code>1y</code>, <code>5 years</code>. You can skip /rate and just type "
        "<code>EUR 20000 5y</code>.\n\n"
        "<b>/rates</b> — the table: each currency, each source, with disagreements marked\n"
        "<b>/diff</b> — the disagreements only, with when each source was last checked\n"
        "<b>/subscribe EUR</b>, <b>/unsubscribe EUR</b> — a message when any source changes a rate; "
        "<b>/subscribe</b> alone lists yours\n"
        "<b>/about</b> — the formula, the sources, tax and the fine print\n\n"
        f"{region} view. <i>{DISCLAIMER}</i>"
    )


def about(region: Region, poll_hours: int) -> str:
    sources = "\n".join(f"• {s.label}" for s in ORDER)
    return (
        f"<b>About</b>\n\n<i>{DISCLAIMER}</i> No logos, no logins, no API keys: only public pages, "
        f"each read once every {poll_hours} hours.\n\n"
        "<b>The formula</b> (from the help centre):\n"
        "<code>daily = balance × ((1 + AER)^(1/365.25) − 1)</code>\n"
        "Each day's interest is paid rounded down to the cent; the fraction is carried to the next "
        f'day, and what is paid is cash, so it compounds. <a href="{FORMULA}">Source</a>.\n\n'
        f"<b>The sources</b> ({region} view, {region.company}):\n{sources}\n"
        "If a source fails, the last value it gave is shown, marked stale, and no alert is sent.\n\n"
        f'<b>Tax.</b> {TAX[region]} The bot shows interest before tax. <a href="{TAX_ARTICLE}">Source</a>.\n\n'
        f'<a href="{REPO}">Source code</a>'
    )


# --- the owner's saved pages ------------------------------------------------------------------


def upload_done(source: SourceId, count: int, changes: Sequence[Change]) -> str:
    changed = "".join(f"\n{c.ccy}: {pct(c.old)} → {pct(c.new)}" for c in changes)
    if not changes:
        return f"Recorded {count} rates from {source.label}. Nothing changed."
    return f"Recorded {count} rates from {source.label}. Different from before:{changed}\nSubscribers were not told."


def upload_failed(reason: str) -> str:
    return f"I could not read that page: {escape(reason)}."
