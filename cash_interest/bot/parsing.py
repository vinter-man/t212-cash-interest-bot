"""`/rate EUR 20000 5y`, and every other way people write it.

A tokenizer, not a guess: the words can come in any order and any case, an amount can be
`20k`, `20 000`, `20,000.50`, `€20000` or `1.5m`, a period `5y`, `6 months` or `30d`. Anything
it does not recognise is named back in the error, and two amounts, two currencies or two
periods are an error rather than a pick.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from cash_interest.calc import CENT, YEAR, Period
from cash_interest.calc.period import Unit

EXAMPLE = "/rate EUR 20000 5y"
MAX_AMOUNT = Decimal(100_000_000)
# The currencies a Trading 212 account can hold; the sources quote a rate for most of them.
CURRENCIES = frozenset(
    ("EUR", "GBP", "USD", "PLN", "CZK", "HUF", "RON", "SEK", "DKK", "NOK", "CHF", "CAD", "BGN", "AUD")
)

_SYMBOLS = {"€": "EUR", "£": "GBP", "$": "USD", "zł": "PLN", "kč": "CZK", "ft": "HUF", "lei": "RON"}
_UNITS: dict[str, Unit] = {
    **dict.fromkeys(("d", "day", "days"), "d"),
    **dict.fromkeys(("w", "wk", "wks", "week", "weeks"), "w"),
    **dict.fromkeys(("m", "mo", "mos", "mon", "month", "months"), "m"),
    **dict.fromkeys(("y", "yr", "yrs", "year", "years"), "y"),
}
_FILLER = frozenset(("for", "over", "in", "at", "of", "on", "with", "and", "per", "a", "an", "rate"))
_MULTIPLIERS = {"k": Decimal(1_000), "m": Decimal(1_000_000)}
# A number written in groups: a head of one to three digits, then groups of exactly three,
# split by spaces or no-break ones. "20 000" and "1 000 000" are one number each; "20000 365d"
# and "500 365d" are an amount and a period.
_GROUPED = re.compile(r"(?<![\d.,])\d{1,3}(?:[ \N{NO-BREAK SPACE}\N{NARROW NO-BREAK SPACE}]\d{3})+(?!\w)")
_PERIOD = re.compile(r"^(\d{1,4})(" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")$")
_AMOUNT = re.compile(r"^(\d[\d.,]*)(k|m)?$")
_CODE = re.compile(r"^[a-z]{3}$")


class InputError(ValueError):
    """The message is for the user, written as a sentence."""


@dataclass(frozen=True, slots=True)
class Query:
    ccy: str
    amount: Decimal
    period: Period = YEAR


def _number(text: str) -> Decimal:
    """20,000.50, 20.000,50, 20,000, 1,5 and 0.5. A separator before exactly three digits groups
    thousands if what comes before it can lead a grouped number (1 to 3 digits, no leading zero);
    the last separator otherwise marks the decimals; anything else is unreadable."""
    *groups, last = re.split(r"[.,]", text)
    if not groups:
        return Decimal(last)
    head, inner_ok = groups[0], all(len(group) == 3 for group in groups[1:])
    leads = len(head) <= 3 and not head.startswith("0")
    if len(last) == 3 and inner_ok and leads:
        return Decimal("".join(groups) + last)
    if last and inner_ok and (len(groups) == 1 or leads):
        return Decimal("".join(groups) + "." + last)
    raise InvalidOperation(text)


def _split_symbol(word: str) -> tuple[str | None, str]:
    for symbol, ccy in _SYMBOLS.items():
        if word.startswith(symbol) and len(word) > len(symbol):
            return ccy, word[len(symbol) :]
        if word.endswith(symbol) and len(word) > len(symbol):
            return ccy, word[: -len(symbol)]
    return None, word


def _is_months_or_millions(word: str) -> bool:
    """`6m`: six months after an amount, six million if it is the only number given."""
    return bool(re.fullmatch(r"\d{1,4}m", word))


def known_currency(word: str, known: Collection[str]) -> str:
    code = word.upper()
    choices = CURRENCIES | set(known)
    if code in choices:
        return code
    hint = difflib.get_close_matches(code, sorted(choices), n=1, cutoff=0.6)
    suggestion = f" Did you mean {hint[0]}?" if hint else ""
    raise InputError(f"{code} is not a currency I know.{suggestion}")


class _Reader:
    def __init__(self, known: Collection[str]) -> None:
        self.known = known
        self.ccy: str | None = None
        self.amount: Decimal | None = None
        self.period: Period | None = None

    def set_ccy(self, ccy: str, word: str) -> None:
        if self.ccy is not None and self.ccy != ccy:
            raise InputError(f"Two currencies, {self.ccy} and {word}. Ask about one at a time.")
        self.ccy = ccy

    def set_amount(self, amount: Decimal, word: str) -> None:
        if self.amount is not None:
            raise InputError(f"Two amounts, {self.amount:,f} and {word}. Which one?")
        if amount <= 0:
            raise InputError("The amount has to be more than zero.")
        if amount > MAX_AMOUNT:
            raise InputError(f"That is more than {MAX_AMOUNT:,}. Try a smaller amount.")
        if amount != amount.quantize(CENT):
            raise InputError(f"{word} has a fraction of a cent; balances are whole cents.")
        self.amount = amount.quantize(CENT)

    def set_period(self, count: str, unit: Unit, word: str) -> None:
        if self.period is not None:
            raise InputError(f"Two periods, {self.period.code} and {word}.")
        try:
            self.period = Period(int(count), unit)
        except ValueError:
            raise InputError(f"{word} is out of range: anything from 1 day to 10 years.") from None

    def amount_from(self, word: str) -> bool:
        ccy, rest = _split_symbol(word)
        match = _AMOUNT.match(rest)
        if match is None:
            return False
        try:
            value = _number(match.group(1)) * _MULTIPLIERS.get(match.group(2) or "", Decimal(1))
        except InvalidOperation:
            raise InputError(f"I could not read {word} as an amount.") from None
        if ccy is not None:
            self.set_ccy(ccy, word)
        self.set_amount(value, word)
        return True

    def read(self, word: str, following: str) -> int:
        """Takes `word` (and sometimes the next one); returns how many words it used."""
        if word.isdigit() and following in _UNITS and len(following) > 1:
            self.set_period(word, _UNITS[following], f"{word} {following}")
            return 2
        if match := _PERIOD.match(word):
            self.set_period(match.group(1), _UNITS[match.group(2)], word)
        elif word in _SYMBOLS:
            self.set_ccy(_SYMBOLS[word], word)
        elif word == "kr":
            raise InputError("kr could be SEK, DKK or NOK. Write the code instead.")
        elif _CODE.match(word):
            self.set_ccy(known_currency(word, self.known), word.upper())
        elif not self.amount_from(word):
            raise InputError(f"I do not understand “{word}”.")
        return 1


def parse_query(text: str, known: Collection[str] = ()) -> Query:
    """The currency, the amount and (optionally) the period: what follows /rate, or a message."""
    joined = _GROUPED.sub(lambda match: "".join(match.group(0).split()), text)
    words = [w.strip(",;") for w in joined.lower().split()]
    words = [w for w in words if w and w not in _FILLER]
    if not words:
        raise InputError("Tell me a currency and an amount.")
    reader = _Reader(known)
    deferred = [w for w in words if _is_months_or_millions(w)]
    rest = [w for w in words if not _is_months_or_millions(w)]
    i = 0
    while i < len(rest):
        i += reader.read(rest[i], rest[i + 1] if i + 1 < len(rest) else "")
    for word in deferred:
        if reader.amount is None and len(deferred) == 1:
            reader.amount_from(word)
        else:
            reader.set_period(word[:-1], "m", word)
    if reader.ccy is None:
        raise InputError("Which currency? Add a code such as EUR or GBP.")
    if reader.amount is None:
        raise InputError("How much? Add an amount such as 20000 or 20k.")
    return Query(reader.ccy, reader.amount, reader.period or YEAR)


def parse_currency(text: str, known: Collection[str] = ()) -> str:
    """The one currency of `/subscribe EUR`, from what follows the command."""
    words = text.split()
    if len(words) != 1:
        raise InputError("One currency code, please.")
    word = words[0].lower()
    if word in _SYMBOLS:
        return _SYMBOLS[word]
    return known_currency(word, known)
