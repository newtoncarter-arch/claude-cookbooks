"""Command-line entry point.

    python -m tradebot.main check   # load config, run safety gate, show mode
    python -m tradebot.main kill    # engage kill switch (cancel all + flatten)

`run` (the live loop) and `backtest` subcommands arrive in later stages.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from tradebot.config import confirm_mode, load_config

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "default.toml"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="tradebot")
    p.add_argument("command", choices=["check", "kill"])
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = p.parse_args(argv)

    load_dotenv()  # reads .env into the environment; .env is git-ignored
    cfg = load_config(args.config)

    if args.command == "kill":
        # Always works, in any mode, without the live prompt: stopping trading
        # should never require extra steps.
        Path(cfg.kill_switch_file).touch()
        from tradebot.execution.factory import make_broker

        make_broker(cfg).flatten()
        print("Kill switch engaged: all orders cancelled, all positions closed.")
        return

    confirm_mode(cfg)
    print(
        f"Config OK. Mode: {cfg.mode.upper()} | broker: {cfg.broker} | strategy: {cfg.strategy.name}"
    )


if __name__ == "__main__":
    main()
