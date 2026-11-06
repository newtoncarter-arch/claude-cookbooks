"""Build the configured strategy. The only place strategy parameters are read."""

from __future__ import annotations

from datetime import time

from tradebot.config import Config
from tradebot.strategy.base import Strategy
from tradebot.strategy.universe_orb import UniverseORB


def make_strategy(cfg: Config) -> Strategy:
    if cfg.strategy.name == "orb":
        from tradebot.strategy.orb import OpeningRangeBreakout

        hh, mm = map(int, cfg.strategy.entry_cutoff.split(":"))
        return OpeningRangeBreakout(
            range_minutes=cfg.strategy.range_minutes,
            bar_minutes=int(cfg.bar_timeframe.removesuffix("Min")),
            entry_cutoff=time(hh, mm),
        )
    raise ValueError(f"Unsupported strategy: {cfg.strategy.name!r}")


def make_universe_strategy(cfg: Config) -> UniverseORB:
    from tradebot.strategy.orb import OpeningRangeBreakout

    orb = make_strategy(cfg)
    assert isinstance(orb, OpeningRangeBreakout)
    return UniverseORB(
        orb,
        watchlist_size=cfg.universe.watchlist_size,
        lookback_days=cfg.universe.lookback_days,
    )
