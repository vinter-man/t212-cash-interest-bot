"""How amounts and rates are written for people. Display only: payments are already whole cents."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}


def _grouped(amount: Decimal, places: int, rounding: str = ROUND_HALF_UP) -> str:
    step = Decimal(1).scaleb(-places)
    return f"{amount.quantize(step, rounding=rounding):,.{places}f}"


def money(amount: Decimal, ccy: str, places: int = 2, rounding: str = ROUND_HALF_UP) -> str:
    """€20,000.00, £1.35, PLN 1,234.56. A negative zero never shows as "-€0.00"."""
    text = _grouped(abs(amount), places, rounding)
    sign = "-" if amount < 0 and text.strip("0.,") else ""
    symbol = SYMBOLS.get(ccy)
    return f"{sign}{symbol}{text}" if symbol else f"{sign}{ccy} {text}"


def fraction(amount: Decimal, ccy: str) -> str:
    """Less than a cent, to two significant digits: €0.0046, €0.000037; zero is €0. Cut rather
    than rounded, so a fraction just short of a cent never shows as a whole one."""
    if amount == 0:
        return money(Decimal(0), ccy, 0)
    places = max(2, min(8, 1 - amount.adjusted()))
    return money(amount, ccy, places, ROUND_DOWN)


def whole(amount: Decimal, ccy: str) -> str:
    """For headings: €20,000 rather than €20,000.00, but €20,000.50 keeps its cents."""
    return money(amount, ccy, 0 if amount == amount.to_integral_value() else 2)


def pct(apy: Decimal) -> str:
    """2.5%, 3.55%, 0.25%: as few digits as the rate needs, like the sources write them."""
    text = f"{(apy * 100).normalize():f}"
    return f"{text}%"


def pct2(apy: Decimal) -> str:
    """Fixed two decimals, for columns: 2.50, 3.55, 0.25."""
    return _grouped(apy * 100, 2)
