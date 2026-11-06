"""Configuration loading and the paper/live safety gate.

Safety rules enforced here:
  1. Default mode is PAPER. A missing or misspelled mode is an error and never
     falls back to live.
  2. Live mode needs BOTH `mode = "live"` in the config file AND a typed
     confirmation at startup from a real terminal. No env var or CLI flag can
     skip the prompt.
  3. Secrets are never read from the config file.
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

VALID_MODES = {"paper", "live"}
LIVE_CONFIRMATION_PHRASE = "I ACCEPT LIVE TRADING RISK"
_SECRET_HINTS = ("key", "secret", "token", "password")


class ConfigError(ValueError):
    pass


class LiveTradingNotConfirmed(RuntimeError):
    pass


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    max_position_pct: float
    flatten_minutes_before_close: int
    account_type: str
    max_day_trades_per_5d: int


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    range_minutes: int
    entry_cutoff: str  # "HH:MM" Eastern


@dataclass(frozen=True)
class Config:
    mode: str
    broker: str
    symbols: tuple[str, ...]
    timezone: str
    bar_timeframe: str
    feed: str
    stale_after_seconds: int
    risk: RiskConfig
    strategy: StrategyConfig
    log_dir: str
    kill_switch_file: str

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"


def _reject_secrets(d: dict, path: str = "") -> None:
    for k, v in d.items():
        if isinstance(v, dict):
            _reject_secrets(v, f"{path}{k}.")
        elif any(h in k.lower() for h in _SECRET_HINTS):
            raise ConfigError(f"'{path}{k}' looks like a secret. Put secrets in .env, not config.")


def parse_config(raw: dict) -> Config:
    _reject_secrets(raw)
    g, d, r, lg, st = (raw.get(s, {}) for s in ("general", "data", "risk", "logging", "strategy"))

    mode = g.get("mode", "paper")
    if mode not in VALID_MODES:
        raise ConfigError(f"mode must be 'paper' or 'live', got {mode!r}")

    try:
        risk = RiskConfig(
            risk_per_trade_pct=float(r["risk_per_trade_pct"]),
            max_daily_loss_pct=float(r["max_daily_loss_pct"]),
            max_open_positions=int(r["max_open_positions"]),
            max_position_pct=float(r["max_position_pct"]),
            flatten_minutes_before_close=int(r["flatten_minutes_before_close"]),
            account_type=str(r["account_type"]),
            max_day_trades_per_5d=int(r["max_day_trades_per_5d"]),
        )
    except KeyError as e:
        raise ConfigError(f"missing required risk setting: {e}") from None
    if risk.account_type not in {"cash", "margin"}:
        raise ConfigError("risk.account_type must be 'cash' or 'margin'")

    if d.get("bar_timeframe", "5Min") not in {"1Min", "5Min"}:
        raise ConfigError("data.bar_timeframe must be '1Min' or '5Min'")

    strategy = StrategyConfig(
        name=st.get("name", "orb"),
        range_minutes=int(st.get("range_minutes", 30)),
        entry_cutoff=st.get("entry_cutoff", "15:00"),
    )
    if strategy.name != "orb":
        raise ConfigError(f"unknown strategy {strategy.name!r}")

    return Config(
        mode=mode,
        broker=g.get("broker", "alpaca"),
        symbols=tuple(g.get("symbols", ["SPY"])),
        timezone=g.get("timezone", "America/New_York"),
        bar_timeframe=d.get("bar_timeframe", "5Min"),
        feed=d.get("feed", "iex"),
        stale_after_seconds=int(d.get("stale_after_seconds", 180)),
        risk=risk,
        strategy=strategy,
        log_dir=lg.get("dir", "logs"),
        kill_switch_file=lg.get("kill_switch_file", "KILL"),
    )


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        return parse_config(tomllib.load(f))


def confirm_mode(
    cfg: Config,
    input_fn: Callable[[str], str] = input,
    is_interactive: Callable[[], bool] = lambda: sys.stdin.isatty(),
) -> None:
    """Run at startup. Returns normally for paper. For live, raises unless confirmed."""
    if cfg.is_paper:
        return
    if not is_interactive():
        raise LiveTradingNotConfirmed(
            "Live mode needs a typed confirmation from an interactive terminal. Refusing to start."
        )
    print("\n*** LIVE TRADING: real money will be at risk. ***")
    print(f"Broker: {cfg.broker} | Symbols: {', '.join(cfg.symbols)}")
    answer = input_fn(f'Type exactly "{LIVE_CONFIRMATION_PHRASE}" to continue: ')
    if answer.strip() != LIVE_CONFIRMATION_PHRASE:
        raise LiveTradingNotConfirmed("Confirmation phrase did not match. Not starting.")
