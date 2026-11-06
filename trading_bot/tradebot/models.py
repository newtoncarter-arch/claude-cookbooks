"""Plain data types shared by every module.

Keeping these broker-agnostic is what lets the strategy, risk, and backtester
code run without knowing which broker (or simulator) is underneath.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalType(str, Enum):
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT = "exit"


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar. `timestamp` is the bar's START time (timezone-aware)."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    """What the strategy wants to do. It has no quantity: sizing belongs to risk."""

    symbol: str
    type: SignalType
    timestamp: datetime  # the time of the bar that produced the signal
    stop_price: float | None = None  # where the strategy says the idea is wrong
    reason: str = ""


@dataclass(frozen=True)
class OrderRequest:
    """A fully sized order, approved by risk, ready for the broker."""

    symbol: str
    side: Side
    qty: int
    stop_loss: float | None = None  # sent to the broker as an attached stop
    client_order_id: str = ""


@dataclass
class Position:
    symbol: str
    qty: int  # negative = short
    avg_entry_price: float


@dataclass
class Account:
    equity: float
    cash: float
    buying_power: float
    day_trade_count: int = 0
    extra: dict = field(default_factory=dict)
