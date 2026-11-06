"""Opening Range Breakout (ORB), long-only.

Rules (all deterministic):
  1. Opening range = high and low of the regular-session bars that START in
     [09:30, 09:30 + range_minutes). With 5-min bars and 30 minutes, that's 6 bars.
  2. If any of those bars is missing, the day is skipped (no guessing).
  3. ENTRY: the FIRST bar after the range whose CLOSE is strictly above the range
     high produces an ENTER_LONG signal, provided that bar ENDS at or before
     `entry_cutoff`. The order fills on the NEXT bar (backtester/broker's job).
  4. STOP: the range low, placed at the broker with the entry.
  5. At most one signal per day. If the first breakout was missed or stopped
     out, there is no re-entry. Because this is derived from today's bars rather than
     stored state, restarting the bot mid-day can't cause a second entry.

Exits are NOT generated here: the broker-side stop handles losers, and the
risk module flattens everything before the close (Stage 4).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from tradebot.models import Bar, Signal, SignalType
from tradebot.strategy.base import Strategy

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)


class OpeningRangeBreakout(Strategy):
    def __init__(
        self,
        range_minutes: int = 30,
        bar_minutes: int = 5,
        entry_cutoff: time = time(15, 0),
    ):
        if range_minutes <= 0 or range_minutes % bar_minutes != 0:
            raise ValueError("range_minutes must be a positive multiple of bar_minutes")
        self.range_minutes = range_minutes  # the ONE tunable parameter
        self.bar_minutes = bar_minutes  # set by data resolution, not tuned
        self.entry_cutoff = entry_cutoff  # fixed in advance, not tuned
        self.bars_in_range = range_minutes // bar_minutes

    # --- helpers -----------------------------------------------------------
    def _et(self, ts: datetime) -> datetime:
        if ts.tzinfo is None:
            raise ValueError("bar timestamps must be timezone-aware")
        return ts.astimezone(ET)

    def _session_minutes(self, ts_et: datetime) -> int:
        """Minutes since 09:30 for the bar's start time."""
        open_dt = datetime.combine(ts_et.date(), SESSION_OPEN, ET)
        return int((ts_et - open_dt).total_seconds() // 60)

    def opening_range(self, today: Sequence[Bar]) -> tuple[float, float] | None:
        """(high, low) of today's opening range, or None if incomplete."""
        rng = [
            b
            for b in today
            if 0 <= self._session_minutes(self._et(b.timestamp)) < self.range_minutes
        ]
        starts = {self._session_minutes(self._et(b.timestamp)) for b in rng}
        expected = set(range(0, self.range_minutes, self.bar_minutes))
        if starts != expected:
            return None  # missing or misaligned bars: skip the day
        high, low = max(b.high for b in rng), min(b.low for b in rng)
        if high <= low:
            return None
        return high, low

    # --- main entry point --------------------------------------------------
    def on_bar(self, history: Sequence[Bar], position_qty: int) -> Signal | None:
        if not history or position_qty != 0:
            return None

        last = history[-1]
        last_et = self._et(last.timestamp)
        today_date = last_et.date()
        today = [b for b in history if self._et(b.timestamp).date() == today_date]

        # Only bars after the range can trigger.
        if self._session_minutes(last_et) < self.range_minutes:
            return None

        # Entry cutoff: the signal bar must END by the cutoff.
        bar_end = (last_et + timedelta(minutes=self.bar_minutes)).time()
        if bar_end > self.entry_cutoff:
            return None

        rng = self.opening_range(today)
        if rng is None:
            return None
        high, low = rng

        # Only the FIRST post-range bar that closes above the high counts.
        post_range = [
            b for b in today if self._session_minutes(self._et(b.timestamp)) >= self.range_minutes
        ]
        first_breakout = next((b for b in post_range if b.close > high), None)
        if first_breakout is None or first_breakout.timestamp != last.timestamp:
            return None

        return Signal(
            symbol=last.symbol,
            type=SignalType.ENTER_LONG,
            timestamp=last.timestamp,
            stop_price=low,
            reason=f"close {last.close:.2f} > opening-range high {high:.2f}; stop {low:.2f}",
        )
