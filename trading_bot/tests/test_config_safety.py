"""Stage 1 tests: paper is the default, and live can't switch on by accident."""

import tomllib
from pathlib import Path

import pytest
from tradebot.config import (
    LIVE_CONFIRMATION_PHRASE,
    ConfigError,
    LiveTradingNotConfirmed,
    confirm_mode,
    load_config,
    parse_config,
)
from tradebot.execution.alpaca_broker import MissingCredentialsError, load_alpaca_credentials

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "default.toml"


def raw(**general):
    d = tomllib.loads(DEFAULT.read_text())
    d["general"].update(general)
    return d


def test_shipped_config_is_paper():
    assert load_config(DEFAULT).mode == "paper"


def test_missing_mode_defaults_to_paper():
    d = raw()
    del d["general"]["mode"]
    assert parse_config(d).is_paper


@pytest.mark.parametrize("bad", ["LIVE", "Live", "production", "real", ""])
def test_unknown_mode_is_rejected_not_treated_as_live(bad):
    with pytest.raises(ConfigError):
        parse_config(raw(mode=bad))


def test_paper_needs_no_prompt():
    confirm_mode(parse_config(raw()), input_fn=lambda _: pytest.fail("prompted in paper"))


def test_live_requires_exact_phrase():
    cfg = parse_config(raw(mode="live"))
    with pytest.raises(LiveTradingNotConfirmed):
        confirm_mode(cfg, input_fn=lambda _: "yes", is_interactive=lambda: True)
    confirm_mode(cfg, input_fn=lambda _: LIVE_CONFIRMATION_PHRASE, is_interactive=lambda: True)


def test_live_refuses_non_interactive_start():
    cfg = parse_config(raw(mode="live"))
    with pytest.raises(LiveTradingNotConfirmed):
        confirm_mode(cfg, input_fn=lambda _: LIVE_CONFIRMATION_PHRASE, is_interactive=lambda: False)


def test_secrets_in_config_are_rejected():
    d = raw()
    d["general"]["api_key"] = "abc"
    with pytest.raises(ConfigError):
        parse_config(d)


def test_missing_risk_limit_is_an_error():
    d = raw()
    del d["risk"]["max_daily_loss_pct"]
    with pytest.raises(ConfigError):
        parse_config(d)


def test_paper_mode_never_reads_live_keys(monkeypatch):
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET_KEY", raising=False)
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "live")
    monkeypatch.setenv("ALPACA_LIVE_SECRET_KEY", "live")
    with pytest.raises(MissingCredentialsError):
        load_alpaca_credentials(is_paper=True)


def test_env_example_has_no_values():
    example = DEFAULT.parent.parent / ".env.example"
    for line in example.read_text().splitlines():
        if line and not line.startswith("#"):
            assert line.endswith("="), f"value present in .env.example: {line}"
