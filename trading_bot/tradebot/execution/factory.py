"""The one place a broker is chosen. Swapping brokers or paper/live is config-only."""

from __future__ import annotations

from tradebot.config import Config
from tradebot.execution.base import Broker


def make_broker(cfg: Config) -> Broker:
    if cfg.broker == "alpaca":
        from tradebot.execution.alpaca_broker import AlpacaBroker

        return AlpacaBroker(is_paper=cfg.is_paper)
    raise ValueError(f"Unsupported broker: {cfg.broker!r}")
