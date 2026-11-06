"""ORB across a stock universe.

Each day:
  1. Pre-market: the data layer supplies today's ELIGIBLE symbols (see data/universe.py).
  2. At 10:00, once the opening range is complete, rank eligible symbols by
     OPENING RELATIVE VOLUME = today's 09:30-10:00 volume divided by the average
     09:30-10:00 volume over the previous `lookback_days` days. Unusually heavy
     opening volume suggests the stock is "in play" (news, earnings), and those
     are the stocks where breakouts are most likely to follow through.
  3. The top `watchlist_size` symbols form today's watchlist. Ties are broken
     alphabetically, so the result is deterministic.
  4. The single-stock ORB rules (strategy/orb.py) run on each watchlist symbol.
     Every breakout is emitted as a candidate signal. The risk module decides
     which, if any, are taken (max open positions, risk budget, whole shares).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from tradebot.models import Bar, Signal
from tradebot.strategy.orb import OpeningRangeBreakout


class UniverseORB:
    def __init__(
        self,
        orb: OpeningRangeBreakout,
        watchlist_size: int = 5,  # fixed in advance, not tuned
        lookback_days: int = 20,  # fixed in advance, not tuned
    ):
        self.orb = orb
        self.watchlist_size = watchlist_size
        self.lookback_days = lookback_days

    def _range_volume_by_day(self, history: Sequence[Bar]) -> dict:
        """{date: opening-range volume} for days with a COMPLETE opening range."""
        by_day: dict = {}
        for b in history:
            et = self.orb._et(b.timestamp)
            if 0 <= self.orb._session_minutes(et) < self.orb.range_minutes:
                by_day.setdefault(et.date(), []).append(b)
        return {
            d: sum(b.volume for b in bars)
            for d, bars in by_day.items()
            if len(bars) == self.orb.bars_in_range
        }

    def opening_relative_volume(self, history: Sequence[Bar], today) -> float | None:
        vols = self._range_volume_by_day(history)
        if today not in vols:
            return None
        prior = [vols[d] for d in sorted(vols) if d < today][-self.lookback_days :]
        if len(prior) < self.lookback_days:
            return None
        avg = sum(prior) / len(prior)
        return vols[today] / avg if avg > 0 else None

    def watchlist(
        self, histories: Mapping[str, Sequence[Bar]], eligible: Sequence[str], today
    ) -> list[str]:
        scored = []
        for sym in eligible:
            h = histories.get(sym)
            if not h:
                continue
            rv = self.opening_relative_volume(h, today)
            if rv is not None:
                scored.append((-rv, sym))  # sort: highest RV first, then A-Z
        return [sym for _, sym in sorted(scored)[: self.watchlist_size]]

    def on_bars(
        self,
        now: datetime,
        histories: Mapping[str, Sequence[Bar]],
        eligible: Sequence[str],
        positions: Mapping[str, int],
    ) -> list[Signal]:
        """Evaluate the bar that STARTED at `now`. Only symbols with a bar at `now`
        are evaluated, so a symbol with no fresh bar can't re-fire an old signal."""
        today = self.orb._et(now).date()
        signals = []
        for sym in self.watchlist(histories, eligible, today):
            h = histories[sym]
            if h[-1].timestamp != now:
                continue
            sig = self.orb.on_bar(h, positions.get(sym, 0))
            if sig:
                signals.append(sig)
        return signals
