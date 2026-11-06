"""Strategy interface. Signal generation ONLY: no broker, no sizing, no I/O."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from tradebot.models import Bar, Signal


class Strategy(ABC):
    @abstractmethod
    def on_bar(self, history: Sequence[Bar], position_qty: int) -> Signal | None:
        """Decide based on `history`, which ends with the bar that just CLOSED.

        The caller passes only bars that already exist, so the strategy has no
        way to see the future. Any order the signal causes fills on the NEXT bar.
        Must be deterministic: same inputs give the same output.
        """
