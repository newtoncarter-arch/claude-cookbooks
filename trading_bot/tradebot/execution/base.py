"""Broker interface. Every broker (and the backtest simulator) implements this."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradebot.models import Account, OrderRequest, Position


class Broker(ABC):
    is_paper: bool

    @abstractmethod
    def get_account(self) -> Account: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> str:
        """Submit an entry with its stop-loss attached AT THE BROKER. Returns order id."""

    @abstractmethod
    def cancel_all_orders(self) -> None: ...

    @abstractmethod
    def close_all_positions(self) -> None: ...

    def flatten(self) -> None:
        """Kill-switch action: cancel everything, then close everything."""
        self.cancel_all_orders()
        self.close_all_positions()
