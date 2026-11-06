"""Which stocks the bot is ALLOWED to trade on a given day.

Run once before the open. Uses only DAILY bars strictly before `as_of`, so the
list can't depend on anything that happens today (no look-ahead).

Survivorship bias: this function is only honest if `daily_bars` includes stocks
that were later delisted or went bankrupt. That's a property of the dataset, not
of this code. Stage 3 has to use a point-in-time dataset.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from tradebot.models import Bar

LISTED_EXCHANGES = frozenset({"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS"})


@dataclass(frozen=True)
class AssetInfo:
    symbol: str
    exchange: str  # e.g. "NASDAQ"; "OTC" is never eligible
    tradable: bool = True
    leveraged_or_inverse: bool = False  # e.g. 3x or -1x ETFs: excluded


@dataclass(frozen=True)
class UniverseRules:
    """Fixed BEFORE looking at any results. None of these is a tuning knob."""

    min_price: float = 5.0  # below $5: penny-stock spreads, manipulation
    max_price: float = 37.50  # = equity x max_position_pct, so 1 share fits the cap
    min_avg_dollar_volume: float = 20_000_000  # liquid enough for tight spreads
    lookback_days: int = 20  # about one trading month


def eligible_symbols(
    daily_bars: Mapping[str, Sequence[Bar]],
    assets: Mapping[str, AssetInfo],
    as_of: date,
    rules: UniverseRules,
) -> list[str]:
    """Symbols eligible to trade on `as_of`, sorted alphabetically."""
    out = []
    for sym, bars in daily_bars.items():
        info = assets.get(sym)
        if info is None or not info.tradable or info.leveraged_or_inverse:
            continue
        if info.exchange.upper() not in LISTED_EXCHANGES:
            continue
        past = [b for b in bars if b.timestamp.date() < as_of]  # strictly before today
        if len(past) < rules.lookback_days:
            continue  # too new to judge
        window = past[-rules.lookback_days :]
        last_close = window[-1].close
        if not (rules.min_price <= last_close <= rules.max_price):
            continue
        avg_dollar_vol = sum(b.close * b.volume for b in window) / len(window)
        if avg_dollar_vol < rules.min_avg_dollar_volume:
            continue
        out.append(sym)
    return sorted(out)


def max_affordable_price(equity: float, max_position_pct: float) -> float:
    """Highest share price where ONE whole share stays within the position cap."""
    return equity * max_position_pct / 100.0
