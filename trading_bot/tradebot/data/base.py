"""Market data interface (historical and live)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime

from tradebot.models import Bar


class MarketDataProvider(ABC):
    @abstractmethod
    def get_historical_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str
    ) -> list[Bar]:
        """Return completed bars in time order. Used by the backtester and for warm-up."""

    @abstractmethod
    def subscribe_bars(self, symbols: list[str], on_bar: Callable[[Bar], None]) -> None:
        """Stream completed live bars. Must only deliver a bar once it has CLOSED."""

    @abstractmethod
    def seconds_since_last_bar(self) -> float:
        """Used by the fail-safe to detect a stale or dropped feed."""
