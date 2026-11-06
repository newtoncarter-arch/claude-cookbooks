"""Alpaca adapter. Order methods are filled in during Stages 4–5.

Credentials come only from environment variables. Paper mode reads ONLY the
paper keys and points at Alpaca's paper endpoint, so live keys can't be used
by accident.
"""

from __future__ import annotations

import os

from tradebot.execution.base import Broker
from tradebot.models import Account, OrderRequest, Position


class MissingCredentialsError(RuntimeError):
    pass


def load_alpaca_credentials(is_paper: bool) -> tuple[str, str]:
    prefix = "ALPACA_PAPER_" if is_paper else "ALPACA_LIVE_"
    key = os.getenv(prefix + "API_KEY", "").strip()
    secret = os.getenv(prefix + "SECRET_KEY", "").strip()
    if not key or not secret:
        raise MissingCredentialsError(
            f"{prefix}API_KEY / {prefix}SECRET_KEY are not set. Put them in .env "
            "(see .env.example). Keys are never read from the config file."
        )
    return key, secret


class AlpacaBroker(Broker):
    def __init__(self, is_paper: bool):
        self.is_paper = is_paper
        self._key, self._secret = load_alpaca_credentials(is_paper)
        self._client = None  # created lazily in Stage 5 with alpaca-py's TradingClient

    def __repr__(self) -> str:  # never print keys
        return f"AlpacaBroker(paper={self.is_paper})"

    def get_account(self) -> Account:
        raise NotImplementedError("Implemented in Stage 5 (paper trading).")

    def get_positions(self) -> list[Position]:
        raise NotImplementedError("Implemented in Stage 5 (paper trading).")

    def submit_order(self, order: OrderRequest) -> str:
        raise NotImplementedError("Implemented in Stage 4/5 (bracket order with broker stop).")

    def cancel_all_orders(self) -> None:
        raise NotImplementedError("Implemented in Stage 4 (kill switch).")

    def close_all_positions(self) -> None:
        raise NotImplementedError("Implemented in Stage 4 (kill switch).")
