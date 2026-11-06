"""Unit tests for the Opening Range Breakout rules."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from tradebot.models import Bar, SignalType
from tradebot.strategy.orb import OpeningRangeBreakout

ET = ZoneInfo("America/New_York")
DAY = datetime(2025, 3, 4, tzinfo=ET).date()


def bar(hhmm: str, o, h, low, c, day=DAY, sym="SPY"):
    hh, mm = map(int, hhmm.split(":"))
    ts = datetime.combine(day, time(hh, mm), ET)
    return Bar(sym, ts, o, h, low, c, 1000)


def opening_range(day=DAY):
    """Six 5-min bars 09:30-09:55. Range high = 101, low = 99."""
    return [
        bar("09:30", 100, 100.5, 99.0, 100.2, day),
        bar("09:35", 100.2, 101.0, 99.8, 100.4, day),
        bar("09:40", 100.4, 100.8, 99.5, 100.0, day),
        bar("09:45", 100.0, 100.6, 99.4, 100.3, day),
        bar("09:50", 100.3, 100.9, 99.9, 100.6, day),
        bar("09:55", 100.6, 100.9, 100.1, 100.7, day),
    ]


@pytest.fixture
def orb():
    return OpeningRangeBreakout(range_minutes=30, bar_minutes=5)


def run_all(strategy, bars, position=0):
    """Feed bars one at a time, as live trading would. Return {bar_time: signal}."""
    out = {}
    for i in range(len(bars)):
        sig = strategy.on_bar(bars[: i + 1], position)
        if sig:
            out[bars[i].timestamp] = sig
    return out


def test_opening_range_values(orb):
    assert orb.opening_range(opening_range()) == (101.0, 99.0)


def test_no_signal_inside_range_even_if_price_rises(orb):
    bars = opening_range()
    bars[-1] = bar("09:55", 100.6, 105, 100.1, 104)  # big move, but still in range window
    assert run_all(orb, bars) == {}


def test_signal_on_first_close_above_high(orb):
    bars = opening_range() + [
        bar("10:00", 100.7, 100.95, 100.5, 100.9),  # below high
        bar("10:05", 100.9, 101.4, 100.8, 101.3),  # first close > 101 -> signal
    ]
    sigs = run_all(orb, bars)
    assert list(sigs) == [bars[-1].timestamp]
    s = sigs[bars[-1].timestamp]
    assert s.type == SignalType.ENTER_LONG
    assert s.stop_price == 99.0


def test_wick_above_high_without_close_is_not_a_signal(orb):
    bars = opening_range() + [bar("10:00", 100.7, 101.8, 100.5, 100.95)]
    assert run_all(orb, bars) == {}


def test_close_exactly_at_high_is_not_a_signal(orb):
    bars = opening_range() + [bar("10:00", 100.7, 101.2, 100.5, 101.0)]
    assert run_all(orb, bars) == {}


def test_only_one_signal_per_day(orb):
    bars = opening_range() + [
        bar("10:00", 100.7, 101.4, 100.6, 101.3),  # breakout #1 -> signal
        bar("10:05", 101.3, 101.4, 100.0, 100.2),  # falls back
        bar("10:10", 100.2, 101.9, 100.1, 101.8),  # breakout #2 -> ignored
    ]
    assert list(run_all(orb, bars)) == [bars[6].timestamp]


def test_no_entry_after_cutoff(orb):
    bars = opening_range()
    t = datetime.combine(DAY, time(10, 0), ET)
    while t.time() < time(14, 55):
        bars.append(Bar("SPY", t, 100.5, 100.8, 100.2, 100.5, 1000))
        t += timedelta(minutes=5)
    # 14:55 bar ends 15:00 -> still allowed; 15:00 bar ends 15:05 -> blocked
    allowed = bars + [bar("14:55", 100.5, 101.5, 100.4, 101.2)]
    blocked = bars + [bar("15:00", 100.5, 101.5, 100.4, 101.2)]
    assert len(run_all(orb, allowed)) == 1
    assert run_all(orb, blocked) == {}


def test_no_signal_while_in_position(orb):
    bars = opening_range() + [bar("10:00", 100.7, 101.4, 100.6, 101.3)]
    assert run_all(orb, bars, position=10) == {}


def test_missing_range_bar_skips_the_day(orb):
    bars = opening_range()
    del bars[2]
    bars.append(bar("10:00", 100.7, 101.4, 100.6, 101.3))
    assert run_all(orb, bars) == {}


def test_previous_day_does_not_leak_into_today(orb):
    prev = DAY - timedelta(days=1)
    yesterday = opening_range(prev) + [bar("10:00", 100.7, 101.4, 100.6, 101.3, prev)]
    today = opening_range() + [bar("10:00", 100.7, 100.95, 100.6, 100.9)]
    sigs = run_all(orb, yesterday + today)
    assert all(ts.date() == prev for ts in sigs)  # only yesterday signalled


def test_naive_timestamps_rejected(orb):
    b = Bar("SPY", datetime(2025, 3, 4, 10, 0), 1, 1, 1, 1, 1)
    with pytest.raises(ValueError):
        orb.on_bar([b], 0)


def test_deterministic(orb):
    bars = opening_range() + [bar("10:00", 100.7, 101.4, 100.6, 101.3)]
    assert run_all(orb, bars) == run_all(OpeningRangeBreakout(), bars)


def test_no_look_ahead_future_bars_cannot_change_past_signals(orb):
    """A signal at time t must be identical no matter what happens after t.

    Two days identical up to 10:05, then wildly different. Every signal up to
    10:05 must match exactly. (The backtester gets its own look-ahead test in
    Stage 3, which checks that fills happen on the NEXT bar.)
    """
    common = opening_range() + [
        bar("10:00", 100.7, 100.95, 100.5, 100.9),
        bar("10:05", 100.9, 101.4, 100.8, 101.3),
    ]
    future_a = [bar("10:10", 101.3, 110, 101, 109)]
    future_b = [bar("10:10", 101.3, 101.3, 90, 91)]
    a = run_all(orb, common + future_a)
    b = run_all(orb, common + future_b)
    cutoff = common[-1].timestamp
    assert {k: v for k, v in a.items() if k <= cutoff} == {
        k: v for k, v in b.items() if k <= cutoff
    }
    assert cutoff in a


def test_factory_builds_orb_from_shipped_config():
    from pathlib import Path

    from tradebot.config import load_config
    from tradebot.strategy.factory import make_strategy

    cfg = load_config(Path(__file__).resolve().parent.parent / "config" / "default.toml")
    s = make_strategy(cfg)
    assert isinstance(s, OpeningRangeBreakout)
    assert (s.range_minutes, s.bar_minutes, s.entry_cutoff) == (30, 5, time(15, 0))
