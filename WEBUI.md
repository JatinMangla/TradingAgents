# TradingAgents Dashboard (`webui/`)

A local web dashboard: launch an analysis, watch each agent finish **live**, and
browse every past run's decision and full reports.

Added on top of upstream v0.3.1 — no upstream behaviour was changed.

## Start it

```powershell
cd D:\git\trading\TradingAgents
.\.venv\Scripts\python.exe -m webui
```

Opens http://localhost:8000 automatically. Stop with Ctrl+C.

| Env var | Default | Purpose |
|---|---|---|
| `WEBUI_HOST` | `127.0.0.1` | Set `0.0.0.0` in Docker/Codespaces |
| `WEBUI_PORT` | `8000` | Port |
| `WEBUI_OPEN` | `1` | `0` to not open a browser |
| `WEBUI_PASSWORD` | — | HTTP Basic password (any username). **Required** for any non-localhost bind |
| `WEBUI_ALLOW_PUBLIC` | — | `1` to bind publicly without a password (only behind a private port or auth proxy) |

Bound to localhost by default — the dashboard can spend your API quota, so it is
not exposed to the network unless you opt in, and then only with a password.

Fresh installs: `pip install ".[webui]"`.

## What it does

**Universal instrument box** — type a ticker *or* a company/index name. The
server resolves it:

* unambiguous (`AAPL`, `RELIANCE.NS`) -> starts immediately;
* ambiguous (`tata motors`, `bitcoin`, `nifty 50`) -> returns candidates and the
  UI opens a chooser so **you** pick, rather than the system guessing and
  silently analysing the wrong company;
* no match -> a clear message with format examples.

Candidates are ranked by instrument type (equities and indices above mutual
funds), exact-symbol and name match, and primary-listing preference. Opaque fund
codes are filtered out. If Yahoo's search finds nothing, the compacted input is
probed directly with `.NS`/`.BO` suffixes — which is how `powerindia` resolves to
`POWERINDIA.NS`. See `TICKERS.md`.

**Two pre-flight checks** before any LLM call is spent:

1. the symbol returns data at all;
2. the symbol has price history *around the analysis date* — a post-demerger
   ticker like `TMCV.NS` trades today but did not exist in 2024, and would
   otherwise fail minutes into the run.

**Readable failures** — provider errors are classified rather than dumped. A
Gemini free-tier refusal (~1.5 KB of nested JSON) becomes "LLM quota exhausted",
an explanation that the free tier allows N requests/day, and concrete fixes.

**Run panel** — ticker, analysis date, and which of the four analysts to include.
One run at a time (concurrent runs would race on the decision log and blow
through free-tier rate limits), so a second request returns HTTP 409.

**Live pipeline** — each agent lights up as it starts and turns green as it
finishes, with an elapsed timer and a feed of tool calls (`get_stock_data`,
`get_verified_market_snapshot`, …) as they happen. Streamed over Server-Sent
Events; reconnecting mid-run replays what you missed.

**Reports** — every section appears as a tab the moment that agent finishes:
Market, Sentiment, News, Fundamentals, Bull, Bear, Research, Trader, the three
Risk debators, and the final Decision. Markdown is rendered client-side.

**Market panel** — live price, change, a 1M/3M/6M/1Y chart with 50/200 SMA
overlays, RSI / MACD / ATR / Bollinger / SMA values, and FRED macro headlines
(CPI, Fed Funds, Unemployment, 10Y) when `FRED_API_KEY` is set.

**Past decisions** — every completed run with rating, realised alpha, price
target and horizon. Click a row to load its full report set and the reflection
written after the outcome was scored.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | dashboard |
| `GET /api/config` | provider/model + which keys are present (booleans only) |
| `GET /api/search?q=` | ranked ticker candidates for a name |
| `GET /api/resolve?q=` | resolve free-form text: resolved / ambiguous / not_found |
| `POST /api/run` | start a run |
| `GET /api/run/{id}` | run snapshot |
| `GET /api/run/{id}/stream` | SSE progress stream |
| `GET /api/history` | past decisions |
| `GET /api/history/{ticker}/{date}` | saved report sections |
| `GET /api/market/{ticker}?period=6mo` | prices, indicators, macro |
| `GET /api/backtest?ticker=&years=` | strategies vs buy-and-hold vs index |
| `GET /api/sip?ticker=&monthly=&years=` | single SIP simulation (XIRR) |
| `GET /api/sip/compare?tickers=&monthly=&years=` | rank instruments by SIP XIRR |
| `GET /api/docs` | auto-generated API docs |

## Design notes

- **Single process, in memory.** A local research tool, not a multi-user service.
  Run state lives in the process; past runs come from disk and survive restarts.
- **Self-contained frontend.** One HTML file, no CDN, no build step, no npm.
  Includes a small markdown renderer and hand-rolled SVG charting.
- **Reuses the CLI's streaming approach** — resolve instrument identity first,
  then iterate `graph.graph.stream(...)`.
- **Read-only endpoints degrade rather than fail**: no FRED key just hides the
  macro tiles; an indicator that cannot be computed shows `—`.
- Ticker and date are validated before touching the filesystem (they land in a
  path), and API key *values* are never returned — only booleans.

## Two upstream quirks this had to work around

1. **`save_reports()` defaults to a different layout than the CLI** —
   `logs/reports/<TICKER>_<timestamp>/` versus the CLI's
   `logs/<TICKER>/<date>/reports/`. The dashboard passes an explicit
   `save_path` so its runs land beside CLI runs and show up in history.
2. **Only `propagate()` writes the decision log** — neither the CLI nor a raw
   `graph.stream()` does. Streaming directly would mean dashboard runs never
   appeared in history and never joined the reflection loop, so the dashboard
   calls `_resolve_pending_entries()` before the run and `store_decision()`
   after, matching what `propagate()` does.

## Verified

- Live runs streamed end to end (AAPL, MSFT) — agent-by-agent progress, tool
  calls, per-section reports, final decision.
- Reports saved to the CLI layout and re-loaded through the history API
  (9 sections incl. bull/bear/risk debates).
- Decisions written to the decision log and appearing in Past decisions.
- Market endpoint returned live prices, all 7 indicators, and 4 FRED series.
- Name search: `nifty 50` -> `^NSEI`, `reliance` -> `RELIANCE.NS`.
- Full run on the `^NSEI` index completed end to end (identity resolved as
  "NIFTY 50", decision Hold), confirming index tickers work, not just equities.
- Project test suite still **576 passed, 2 skipped**.
