"""Tests for the eligible-stock filter and the multi-stock ORB watchlist."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from tradebot.data.universe import (
    AssetInfo,
    UniverseRules,
    eligible_symbols,
    max_affordable_price,
)
from tradebot.models import Bar, SignalType
from tradebot.strategy.orb import OpeningRangeBreakout
from tradebot.strategy.universe_orb import UniverseORB

ET = ZoneInfo("America/New_York")
TODAY = date(2025, 3, 31)  # a Monday
RULES = UniverseRules(min_price=5, max_price=37.5, min_avg_dollar_volume=20e6, lookback_days=20)


def daily(sym, close, volume, n=25, end=TODAY):
    """n daily bars ending the day BEFORE `end`."""
    days = [end - timedelta(days=i) for i in range(n, 0, -1)]
    return [
        Bar(sym, datetime.combine(d, time(9, 30), ET), close, close, close, close, volume)
        for d in days
    ]


def listed(sym, **kw):
    return AssetInfo(sym, kw.pop("exchange", "NASDAQ"), **kw)


# ---------------------------------------------------------------- eligibility
def test_max_price_comes_from_capital_and_cap():
    assert max_affordable_price(150, 25) == 37.5


@pytest.mark.parametrize(
    "close,volume,info,ok",
    [
        (20.0, 2_000_000, listed("X"), True),  # $40M/day, $20: eligible
        (4.99, 10_000_000, listed("X"), False),  # under $5
        (37.51, 2_000_000, listed("X"), False),  # one share exceeds the 25% cap
        (20.0, 500_000, listed("X"), False),  # only $10M/day
        (20.0, 2_000_000, listed("X", exchange="OTC"), False),  # OTC
        (20.0, 2_000_000, listed("X", leveraged_or_inverse=True), False),  # 3x ETF
        (20.0, 2_000_000, listed("X", tradable=False), False),  # halted/not tradable
    ],
)
def test_eligibility_rules(close, volume, info, ok):
    got = eligible_symbols({"X": daily("X", close, volume)}, {"X": info}, TODAY, RULES)
    assert (got == ["X"]) is ok


def test_too_little_history_is_excluded():
    got = eligible_symbols({"X": daily("X", 20, 2e6, n=10)}, {"X": listed("X")}, TODAY, RULES)
    assert got == []


def test_eligibility_ignores_todays_bar():
    """Adding a bar dated TODAY (e.g. a price spike) must not change the list."""
    bars = daily("X", 20, 2e6)
    spike = Bar("X", datetime.combine(TODAY, time(9, 30), ET), 99, 99, 99, 99, 1)
    a = eligible_symbols({"X": bars}, {"X": listed("X")}, TODAY, RULES)
    b = eligible_symbols({"X": bars + [spike]}, {"X": listed("X")}, TODAY, RULES)
    assert a == b == ["X"]


# ---------------------------------------------------------------- watchlist
def intraday_day(sym, d, range_vol, breakout_close=None):
    """Opening range 09:30-09:55 (high 101, low 99) with `range_vol` total volume,
    plus a 10:00 bar that closes at `breakout_close` (default: inside range)."""
    per = range_vol / 6
    bars = []
    for i in range(6):
        ts = datetime.combine(d, time(9, 30), ET) + timedelta(minutes=5 * i)
        bars.append(Bar(sym, ts, 100, 101 if i == 1 else 100.5, 99 if i == 0 else 99.5, 100, per))
    c = breakout_close if breakout_close is not None else 100.5
    ts = datetime.combine(d, time(10, 0), ET)
    bars.append(Bar(sym, ts, 100.5, max(c, 100.6), 100.4, c, 1000))
    return bars


def history(sym, today_range_vol, normal_vol=6000, breakout_close=None, days=20):
    h = []
    for i in range(days, 0, -1):
        h += intraday_day(sym, TODAY - timedelta(days=i), normal_vol)
    return h + intraday_day(sym, TODAY, today_range_vol, breakout_close)


@pytest.fixture
def uorb():
    return UniverseORB(OpeningRangeBreakout(), watchlist_size=2, lookback_days=20)


def test_relative_volume(uorb):
    assert uorb.opening_relative_volume(history("A", 18000), TODAY) == pytest.approx(3.0)


def test_relative_volume_needs_full_lookback(uorb):
    assert uorb.opening_relative_volume(history("A", 18000, days=5), TODAY) is None


def test_watchlist_ranks_by_relative_volume_then_symbol(uorb):
    h = {
        "A": history("A", 12000),  # RV 2
        "B": history("B", 30000),  # RV 5
        "C": history("C", 12000),  # RV 2 (tie with A -> A wins alphabetically)
        "D": history("D", 6000),  # RV 1
    }
    assert uorb.watchlist(h, ["A", "B", "C", "D"], TODAY) == ["B", "A"]


def test_ineligible_symbol_never_trades(uorb):
    h = {"A": history("A", 60000, breakout_close=101.5)}
    now = h["A"][-1].timestamp
    assert uorb.on_bars(now, h, eligible=[], positions={}) == []


def test_only_watchlist_symbols_signal(uorb):
    h = {
        "A": history("A", 30000, breakout_close=101.5),  # RV 5, breaks out
        "B": history("B", 24000, breakout_close=101.5),  # RV 4, breaks out
        "C": history("C", 7000, breakout_close=101.5),  # RV 1.17, not on watchlist
    }
    now = h["A"][-1].timestamp
    sigs = uorb.on_bars(now, h, ["A", "B", "C"], positions={})
    assert sorted(s.symbol for s in sigs) == ["A", "B"]
    assert all(s.type == SignalType.ENTER_LONG and s.stop_price == 99 for s in sigs)


def test_stale_symbol_does_not_refire(uorb):
    h = {"A": history("A", 30000, breakout_close=101.5)}
    later = h["A"][-1].timestamp + timedelta(minutes=5)  # A has no bar at `later`
    assert uorb.on_bars(later, h, ["A"], positions={}) == []


def test_watchlist_ignores_future_bars(uorb):
    """Bars after 10:00 (e.g. a huge volume spike at 11:00) can't change today's ranking."""
    base = {"A": history("A", 12000), "B": history("B", 9000)}
    spiked = {k: list(v) for k, v in base.items()}
    spiked["B"].append(Bar("B", datetime.combine(TODAY, time(11, 0), ET), 100, 100, 100, 100, 1e9))
    assert uorb.watchlist(base, ["A", "B"], TODAY) == uorb.watchlist(spiked, ["A", "B"], TODAY)
