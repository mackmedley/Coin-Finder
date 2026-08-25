# Coin-Finder

A meme coin **screener and exit-signal tool** for people who trade manually on FOMO.

It does two things:

1. **`scan`** — pulls live DEX pair data, throws out anything that fails hard safety filters, and ranks what's left with a transparent 0–100 score.
2. **`check`** — watches the positions you've entered and tells you when a mechanical exit rule fires (take profit, stop loss, trailing stop, liquidity collapse, momentum decay).

It **places no orders and holds no funds**. There is no wallet, no private key, and no API credential anywhere in this repo. You read the output and place every trade yourself in FOMO.

---

## Easiest way to run it — nothing to install

Double-click **`Coin Finder.html`**. It opens in your browser and works with no
Python, no installer, and no setup. Positions are saved in that browser.

It runs the same rules as the Python version: `Coin Finder.html` carries a
JavaScript port of `scoring.py` and `sell.py`, and `tests/test_js_parity.py`
scores a spread of payloads through both engines and fails if any score,
component, flag, or rejection reason differs.

One caveat: some browsers refuse cross-site requests from a file opened off
your disk. If the page says it can't reach the price data, use the Python
version below — it has no such restriction.

---

## Running the Python version

Double-click **`Coin Finder.command`** (macOS/Linux) or **`Coin Finder.bat`** (Windows).

It checks for Python, installs the two dependencies on first run, and opens a
menu — scan, check positions, track a buy — with no commands to type. Requires
Python 3.10+ from [python.org](https://python.org/downloads); on Windows, tick
**"Add Python to PATH"** during install.

On macOS, the first double-click may be blocked as an unidentified developer:
right-click the file → **Open** → **Open**. That's needed once.

Everything below is the terminal equivalent, for when you want the extra flags.

---

## Install

```bash
pip install -r requirements.txt
```

Python 3.10+. The only runtime dependencies are `requests` and `PyYAML`.

Optionally install the CLI onto your path:

```bash
pip install -e .
```

Then `coinfinder ...` works anywhere. Without it, use `python3 -m coinfinder.cli ...` from the repo root.

---

## Usage

### Find something to buy

```bash
coinfinder scan
coinfinder scan --limit 20          # show more rows
coinfinder scan --json              # machine-readable, for piping elsewhere
```

```
BUY CANDIDATES  —  3 passed filters, 41 rejected
====================================================================================
 #  SCORE  SYMBOL       CHAIN             PRICE      LIQ    VOL24      1H%   AGE
------------------------------------------------------------------------------------
 1   81.5  WOJAK        solana         $0.00012    $220K    $1.4M   +34.0%   14h
      liquidity=0.86  turnover=1.00  momentum=0.36  buy_pressure=0.98  age_fit=1.00  safety=1.00
      https://dexscreener.com/solana/P1
```

Every score is shown with its component breakdown, so you can see *why* something ranked where it did rather than trusting a single number. Warning signs appear as `flags:` lines — `no socials/website`, `FDV 40x liquidity`, `already pumped 780% in 1h`, `volume fading`.

Each scan is archived to `data/scan_history/` so you can go back later and check whether the things it liked actually worked out.

### Track a position you opened

After you buy on FOMO, mirror the trade so the sell engine knows your entry:

```bash
coinfinder track --chain solana --pair <pair-address> --amount 250
coinfinder track --chain solana --pair <pair-address> --amount 250 --entry-price 0.00012
```

The pair address is the last segment of the DexScreener URL. Entry price defaults to the current live price; pass `--entry-price` if you got a different fill.

### Check whether to sell

```bash
coinfinder check
```

```
 ! SELL         WOJAK          +200.0%  (+2,000.00 USD)  held 5.0h
                entry $0.0001  →  now $0.0003   peak $0.0005   liq -20%
                - take profit hit: +200.0% (target +60%)
                - trailing stop: down -40% from peak $0.0005 (limit -30%)

!! URGENT SELL  DOGGO            -5.0%  (   -25.00 USD)  held 9.0h
                - liquidity down -70% since entry ($100,000 → $30,000) — possible rug
```

Run it on a loop while you're in trades — e.g. `watch -n 120 coinfinder check`, or a cron entry every few minutes.

### Stop tracking

```bash
coinfinder positions            # list what's tracked (no network calls)
coinfinder untrack solana:PAIR1
```

---

## How the buy score works

Six components, each normalized to 0–1, combined by the weights in `config/default.yaml`:

| Component | Weight | What it measures |
|---|---:|---|
| `liquidity` | 15 | Pool depth. Square-rooted — clearing the floor matters far more than the top end. |
| `turnover` | 20 | 24h volume ÷ liquidity. Separates real trading from a ghost pool. |
| `momentum` | 25 | Blended 1h/6h price change, **peaking at the late-pump threshold and decaying past it**. Something up 800% in an hour is scored as late, not as strong. |
| `buy_pressure` | 20 | Share of 1h trades that are buys, scaled down when the sample is small. A 6-of-7 buy ratio off seven trades means nothing. |
| `age_fit` | 10 | Rewards the window where a coin has proven it isn't an instant rug but hasn't gone stale. |
| `safety` | 10 | Rug-risk proxy: FDV/liquidity overhang, missing socials, thin pool, net 24h selling, fading volume. |

Before any of that runs, **hard filters** drop candidates outright — below minimum liquidity or volume, too new, too old, extreme FDV-to-liquidity ratio, or dominated by sellers. These are not tradeable against a high score: a coin you can't exit is worthless no matter how good it looks.

An empty scan is a normal, healthy result. Most scans should reject almost everything.

## How the sell rules work

Rules are evaluated in severity order and the most severe wins:

| Verdict | Fires when |
|---|---|
| `URGENT SELL` | Pool liquidity dropped past `liquidity_drop_pct` since your entry — possible rug or exit scam. |
| `SELL` | Take profit hit, stop loss hit, or trailing stop from the post-entry peak. |
| `TRIM` | Volume collapsed relative to the 24h hourly average, or sellers have taken over the last hour. |
| `HOLD` | Nothing triggered. |

A liquidity collapse **outranks** a profit target on purpose: if the pool is draining, your take-profit number no longer matters because the exit may not be fillable.

The peak price only ratchets upward, and it's persisted, so the trailing stop survives across runs.

---

## Configuration

Everything tunable lives in `config/default.yaml` — filter thresholds, scoring weights, sell rules, which chains to scan. Don't edit it directly; write your own file with just the keys you want to change and it deep-merges over the defaults:

```yaml
# my-config.yaml
filters:
  min_liquidity_usd: 50000
sell_rules:
  take_profit_pct: 100
```

```bash
coinfinder --config my-config.yaml scan
```

Weights are normalized internally, so changing one never silently rescales the others.

## Data source

[DexScreener](https://dexscreener.com)'s public API — free, no key. Discovery combines two feeds: the **token boost** list (paid promotion, a decent proxy for what's being pushed right now, which is where meme coin flow actually originates) and **keyword search** (to catch pairs that aren't paying for boosts). Requests are rate limited, retried with backoff, and time out rather than hanging.

The provider is isolated behind `coinfinder/datasources/`, so adding Birdeye, GeckoTerminal, or a social-sentiment feed later means writing one module that returns `Candidate` objects — nothing else changes.

## Tests

```bash
python3 -m pytest tests -q
```

43 tests covering filters, every scoring component, all sell rules, position
persistence, config validation, provider response-shape handling, menu input
parsing, and Python/JavaScript scoring parity. They run against synthetic
fixtures and make no network calls. The parity test skips if Node isn't
installed.

---

## Read this before trading

- **This is not financial advice.** It's a data tool that ranks and alerts.
- **The score is a relative ranking of one scan's candidates, not a probability of profit.** A high score means "better than the other things this scan found," which may still be terrible.
- **Meme coins are extremely high risk. Most go to zero.** Rug pulls, honeypots that block selling, and sniper bots that front-run you are routine, not exotic.
- **The safety component is a heuristic, not a contract audit.** It cannot detect a honeypot, a malicious mint authority, or an unlocked LP. Check those yourself before buying anything.
- **Never trade money you can't lose entirely.**

Verify every token independently. The tool narrows the field; it does not make the decision.
