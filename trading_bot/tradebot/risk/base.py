"""Risk interface. Full rules arrive in Stage 4. Kill-switch detection is here now."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from tradebot.models import Account, OrderRequest, Position, Signal


class RiskManager(ABC):
    @abstractmethod
    def evaluate(
        self, signal: Signal, account: Account, positions: list[Position], price: float
    ) -> OrderRequest | None:
        """Turn a signal into a sized order, or reject it (None) if any limit would break."""

    @abstractmethod
    def trading_halted(self) -> bool:
        """True after daily-loss limit, kill switch, or a fail-safe trip."""


def kill_switch_engaged(path: str | Path) -> bool:
    """The kill switch is simply a file. `touch KILL` from any terminal engages it."""
    return Path(path).exists()
