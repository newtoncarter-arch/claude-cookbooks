# tradebot: a paper-first intraday trading bot

**Status:** Stage 1 approved. Stage 2 (Opening Range Breakout strategy) is ready for review. No backtester or order code exists yet.

## Strategy: Opening Range Breakout (long-only), `tradebot/strategy/orb.py`

1. **Opening range:** the high and low of the 5-min bars starting 09:30–09:55 ET. If any of those bars is missing, the day is skipped.
2. **Entry:** the *first* later bar that closes strictly above the range high, and ends by 15:00, triggers a buy at the next bar's open.
3. **Stop:** the range low, held at the broker.
4. **Exit:** the stop, or the end-of-day flatten (risk module, Stage 4).
5. **One signal per day:** no re-entry after a stop-out. This is worked out from today's bars, not stored state, so a restart can't cause a second entry.

Tunable parameter: `range_minutes` (30). Fixed in advance: stop at the range low, 15:00 entry cutoff.
Half-days (13:00 close) will be skipped entirely via the exchange calendar (Stage 3).

### Which stocks (`data/universe.py`, `strategy/universe_orb.py`)
1. **Before the open:** eligible = exchange-listed, tradable, not leveraged/inverse, and over the previous 20 days: last close of at least $5 and at most **equity x max position %** ($150 x 25% = **$37.50**), with average daily traded value of at least $20M. Only data from *before* today is used.
2. **At 10:00:** rank eligible stocks by opening relative volume (today's 09:30–10:00 volume divided by its 20-day average). The top 5 form the watchlist. Ties are broken alphabetically.
3. The ORB rules run on each watchlist stock. Every breakout is a *candidate*, and the risk module (Stage 4) decides which to take: max 1 open position, a $0.75 risk budget, whole shares only.

Fixed in advance, not tuned: $5 floor, $20M liquidity, 20-day lookback, watchlist of 5. Changing them after seeing backtest results would be overfitting.

## Assumptions (please confirm or change)

| Setting | Assumed | Why |
|---|---|---|
| Broker | **Alpaca** | Free paper account, official Python SDK (`alpaca-py`), commission-free US stocks and ETFs, and bracket orders, so the stop-loss sits at the broker. |
| Market | **Filtered US stocks and ETFs** (decided) | Exchange-listed, $5 to (equity x 25%), at least $20M/day average traded value, no OTC, no leveraged/inverse ETFs. SPY is the benchmark. |
| Capital | **$150** | Below the price of one SPY share. See "Capital problem" below. |
| Account | **cash** | Safest default (see below). |
| Runs on | **laptop** | Fine for paper trading. A small cloud VM is better for live trading. |
| Level | **beginner** | Explanations are written at that level. |

## Capital ($150): what it means

- **Decided:** whole shares only, so the stop-loss is always held at the broker. Max position stays at 25%, so only stocks priced $5–$37.50 qualify.
- **Expect many trades to be rejected.** Stocks that are "in play" often have opening ranges of 3–8%. On a $30 stock that's $0.90–$2.40 of risk for one share, above the $0.75 (0.5%) budget. The risk module will skip those, and the backtest will report how often that happens.
- **Low-priced stocks have proportionally wider spreads.** One cent on a $10 stock is 0.1%, ten times more than on SPY. The cost model in Stage 3 must reflect that.
- **Dollar outcomes are tiny:** about $0.75 risked per trade and $3 max daily loss. Treat this as a learning project.
- **Survivorship bias is now a real issue.** A stock universe can only be backtested honestly with data that includes delisted companies. Alpaca's free data may not include them. I'll check in Stage 3, and if it doesn't, I'll tell you and say what a proper dataset costs.

## Account rules (checked November 2026)

- **The pattern-day-trader rule is being retired.** On April 14, 2026 the SEC approved FINRA's change to Rule 4210. It removes the PDT designation and the $25,000 minimum and replaces them with an intraday margin standard. The rule took effect June 4, 2026, **but brokers are phasing it in, possibly through 2027.** Check Alpaca's current policy for your account before going live. The bot reads `day_trade_count` from the broker and supports a configurable cap (`max_day_trades_per_5d`) for as long as your broker still enforces the old limit (under the old rule, a margin account under $25k could make at most 3 day trades in 5 business days).
- **Cash accounts were never subject to PDT**, but they have a different limit: you can only trade with *settled* cash. US stocks settle T+1, so money from a sale isn't available to trade with again until the next business day. Breaking this rule ("good-faith" or "free-riding" violations) can freeze the account for 90 days. Stage 4 will track settled cash for cash accounts.

## How it fits together (plain English)

Think of the bot as a production line where each station does one job and can't do anyone else's:

```
 data ──bars──▶ strategy ──signal──▶ risk ──sized order──▶ execution ──▶ broker
                 ("I'd buy")         ("OK, 12 shares,      (Alpaca paper,
                                      stop at $512.40")     Alpaca live, or simulator)
                                         │
 every step ─────────────────────────────┴──────────▶ event log (logs/*.jsonl)
```

- **data/** fetches price bars. A bar is passed on only *after it has closed*, which is the first defense against look-ahead bias.
- **strategy/** looks at past bars and says "enter long", "enter short", "exit", or nothing. It can't place orders, doesn't know the account size, and doesn't know which broker is in use. So the *exact same strategy code* runs in the backtest, in paper trading, and live.
- **risk/** is the gatekeeper. It decides how many shares to trade, or rejects the trade entirely (daily loss limit hit, too many open positions, kill switch on, data feed stale). Nothing reaches the broker without passing through here.
- **execution/** defines one `Broker` interface (submit, cancel all, close all, positions, account). Alpaca is one implementation. In Stage 3 the backtester gets a simulated one that fills on the *next* bar with costs added. `execution/factory.py` is the only place a broker gets chosen.
- **backtest/** (Stage 3) replays history through strategy and risk into the simulated broker.
- **reporting/** writes one JSON line per event (signal, order, fill, P&L, alert). The Stage 5 weekly report will compare these logs with the backtest.

## Safety design (already built and tested)

1. **Paper by default.** The shipped config says `mode = "paper"`. A missing mode means paper. A misspelling like `"LIVE"` or `"production"` is an **error**, never live.
2. **Live trading takes two deliberate steps:** `mode = "live"` in the config file **and** typing `I ACCEPT LIVE TRADING RISK` at startup in a real terminal. No command-line flag or environment variable can skip the prompt, and a non-interactive start (cron, systemd) is refused.
3. **Separate paper and live keys.** Paper mode reads only `ALPACA_PAPER_*`, so live keys can't be used by accident.
4. **No secrets in config.** Any config key that looks like `*key*`, `*secret*`, `*token*`, or `*password*` is rejected. Keys live in `.env`, which is git-ignored.
5. **Kill switch:** `python -m tradebot.main kill` (or create a file named `KILL`). It works in any mode with no confirmation prompt, because stopping should be easy. The broker-side cancel and flatten calls come in Stage 4.

## Layout

```
trading_bot/
├── config/default.toml        # all settings except secrets
├── .env.example               # copy to .env, add Alpaca paper keys
├── tradebot/
│   ├── models.py              # Bar, Signal, OrderRequest, Position, Account
│   ├── config.py              # loading, validation, paper/live gate
│   ├── main.py                # CLI: check, kill (run/backtest later)
│   ├── strategy/orb.py        # single-stock ORB rules
│   ├── strategy/universe_orb.py # daily watchlist + ORB across stocks
│   ├── data/universe.py       # which stocks are eligible each day
│   ├── data/base.py           # MarketDataProvider interface
│   ├── strategy/base.py       # Strategy interface
│   ├── risk/base.py           # RiskManager interface + kill-switch check
│   ├── execution/{base,factory,alpaca_broker}.py
│   ├── backtest/              # Stage 3
│   └── reporting/event_log.py # JSONL event log
└── tests/test_config_safety.py
```

## Try it

```bash
cd trading_bot
cp .env.example .env            # add paper keys from app.alpaca.markets (Paper account)
uv run python -m tradebot.main check
uv run pytest tests -q
```

## Known weaknesses to deal with later

- **Alpaca's free data feed is IEX only**, about 2–3% of US volume. Its bars differ from the consolidated (SIP) tape. For backtesting I'll use SIP historical data, which Alpaca's free tier allows for data older than 15 minutes. Paper and live trading on IEX bars will drift a little from the backtest, and the Stage 5 report should measure how much.
- **Alpaca's paper fills are optimistic.** They don't model queue position or partial fills realistically, so paper results are an upper bound on live results.
- **A laptop that sleeps or loses Wi-Fi can't manage positions.** The broker-side stop-loss limits the damage, but a VM is recommended before going live.
