# What to type in the instrument box

**In the dashboard you can type anything** — a ticker (`AAPL`), a company name
(`hitachi energy`), or an index name (`nifty 50`). If it is unambiguous the run
starts; if several instruments match, you are asked which one you meant and pick
from a list. Nothing is guessed silently.

The rest of this file matters for the **CLI and `main.py`**, which still need an
exact Yahoo ticker, and for understanding what the chooser is offering you.

## The rule

A ticker must match `^[A-Za-z0-9.^=-]{1,24}$` — letters, digits, `.`, `^`, `=`,
`-`. **No spaces.** This is a deliberate security check (`safe_ticker_component`
in `tradingagents/dataflows/utils.py`): tickers become directory names, and
without it a value like `../../etc/foo` would escape the results directory.

## Cheat sheet

### India
| You want | Type |
|---|---|
| NIFTY 50 index | `^NSEI` |
| SENSEX | `^BSESN` |
| Bank Nifty | `^NSEBANK` |
| Reliance Industries | `RELIANCE.NS` |
| TCS | `TCS.NS` |
| Any NSE stock | `<SYMBOL>.NS` |
| Any BSE stock | `<SYMBOL>.BO` |

### Other markets
| Market | Suffix | Example |
|---|---|---|
| US | none | `AAPL`, `NVDA`, `SPY` |
| Hong Kong | `.HK` | `0700.HK` |
| Tokyo | `.T` | `7203.T` |
| London | `.L` | `AZN.L` |
| Toronto | `.TO` | `SHOP.TO` |
| Australia | `.AX` | `BHP.AX` |
| Shanghai / Shenzhen | `.SS` / `.SZ` | `600519.SS` |
| Crypto | `-USD` | `BTC-USD`, `ETH-USD` |

### US index tickers
`^GSPC` (S&P 500), `^DJI` (Dow), `^IXIC` (Nasdaq), `^VIX` (volatility).
ETF proxies often work better for analysis: `SPY`, `QQQ`, `DIA`.

## Notes

- **Indices work but are thinner.** `^NSEI` runs fine end to end, but an index
  has no balance sheet or insider transactions, so the Fundamentals analyst has
  little to work with. For index analysis prefer the Market and News analysts,
  or use an ETF proxy instead.
- **The benchmark auto-resolves per market.** `.NS` tickers are scored against
  the Nifty 50, `.T` against the Nikkei, US tickers against SPY — so the alpha
  figure in Past decisions is the right comparison automatically.
- **Verify a symbol quickly** by typing it in the Ticker box: if the Market
  panel populates with a price and indicators, the pipeline can run it.

## Watch out: same company, several listings

Searching a name often returns more than one real answer, and they are not
interchangeable:

| Query | Candidates | Note |
|---|---|---|
| `tata motors` | `TMCV.NS`, `TMPV.NS` | commercial vs passenger vehicles, post-demerger |
| `hitachi energy` | `POWERINDIA.NS`, `POWERINDIA.BO` | NSE vs BSE listing of the same company |
| `bitcoin` | `BTC-USD`, `BTC-EUR`, `BTC=F` | spot in different currencies, or futures |
| `nifty 50` | `^NSEI`, ETF proxies | the index itself vs funds tracking it |

Prefer the **NSE (.NS)** listing for Indian equities — it is usually the more
liquid one and the benchmark maths is built around it.

## Dates matter too

A ticker can exist today but not at your analysis date. `TMCV.NS` came from the
2025 Tata Motors demerger, so it has no 2024 history — the dashboard blocks that
combination up front and tells you to pick a later date. Recent IPOs behave the
same way.

## Common mistake: missing the exchange suffix

A bare Indian symbol looks valid (no spaces, passes validation) but has no data
behind it on Yahoo:

| Typed | Result |
|---|---|
| `POWERINDIA` | no data — run used to fail minutes in with `NoMarketDataError` |
| `POWERINDIA.NS` | works — Hitachi Energy India Ltd |

The dashboard now runs a pre-flight data check before starting, so a symbol with
no data is rejected immediately with the likely correct one suggested, instead of
burning LLM calls and failing partway through.

## Why not use a broker API (Groww / Zerodha) instead?

Considered and rejected. Broker APIs give **OHLC, live quotes and order
placement for Indian markets** — they do not give company news, fundamentals, or
macro, which is what three of the four analysts actually consume. Groww's API
also needs a paid subscription and only has history from 2020.

Yahoo already covers NSE/BSE fully, including fundamentals. A broker API would
only make sense if the goal became *placing real orders*, which this project
deliberately does not do.
