# PROJECT_CONTEXT.md — session context primer

> **Purpose:** everything an AI assistant (or a future you) needs to resume work on
> this project without re-deriving it. Read this first; it is written to save
> tokens by front-loading facts that are expensive to rediscover.
>
> Companion docs: `FEATURES.md` (what the project can do, source-derived),
> `RUN_LOCAL.md` (how to run it), `WEBUI.md` (the local web dashboard),
> `TICKERS.md` (what the ticker box accepts),
> **`INVESTING.md`** (measured evidence on timing vs holding, SIP vs lump sum —
> read before promising the user any profit feature).
>
> Last updated: 2026-08-24

---

## 1. Environment facts

| Fact | Value |
|---|---|
| Project root | `D:\git\trading\TradingAgents` |
| Repo | https://github.com/TauricResearch/TradingAgents (v0.3.1) |
| OS | Windows 11 Enterprise, PowerShell 5.1 |
| **Admin rights** | **None.** Office laptop. |
| Python | 3.12.10 at `%LOCALAPPDATA%\Programs\Python\Python312` |
| Venv | `.venv\` in project root |
| Install mode | **editable** (`pip install -e .`) |

### The admin-rights workaround (important)

Python was **not** installed on this machine, and there are no admin credentials.

- `winget install Python.Python.3.11` → **fails, exit 1602** (wants elevation)
- Downloading python.org installer and running with
  `/quiet InstallAllUsers=0 PrependPath=1` → **works, exit 0, no admin needed**

Do not waste time on winget or Microsoft Store here. `python`/`python3` on PATH
are Store *stubs* that print "Python was not found" — ignore them and always call
`.\.venv\Scripts\python.exe` explicitly.

---

## 2. How to run

```powershell
cd D:\git\trading\TradingAgents
.\.venv\Scripts\tradingagents.exe        # interactive CLI
.\.venv\Scripts\python.exe main.py       # scripted run (ticker/date inside main.py)
.\.venv\Scripts\python.exe -m cli.main   # CLI from source
.\.venv\Scripts\python.exe -m pytest -q  # test suite
```

No venv activation needed. Direct paths avoid PowerShell execution-policy prompts.

---

## 3. API key status

| Key | Status | Notes |
|---|---|---|
| `GOOGLE_API_KEY` | **SET, verified live** | `AQ.` format (new AI Studio). Free tier. |
| `FRED_API_KEY` | **SET, verified end-to-end** | 32-char. Real CPI/FEDFUNDS reach the news report. |
| `ALPHA_VANTAGE_API_KEY` | empty | Free, 25 req/day. Optional. |

Keys live in `.env`, which **is gitignored** (`.gitignore:151`) — it will NOT
travel to Codespaces. Use Codespaces Secrets there.

Config: provider `google`, deep `gemini-3.5-flash`, quick `gemini-3.1-flash-lite`,
1 debate round, 1 risk round, 6 LLM retries.

---

## 4. Verified findings — do not re-investigate

These were tested empirically. Trust them; re-testing burns tokens and quota.

### StockTwits 403 — DEAD, no free fix
Tested project UA **and** browser UA against
`api.stocktwits.com/api/2/streams/symbol/NVDA.json`. **Both return 403.**
The formerly keyless public API is now OAuth-only. Not a code bug. Not
header-fixable. Do not attempt UA spoofing — it does not work and would be
evading their access control.

### Reddit 429 — IP throttling, NOT a pacing bug
`fetch_reddit_posts` already paces at `inter_request_delay=1.0` with 429 backoff.
**Tested raising it to 4.0s → got WORSE** (2 subreddits failed vs 1). This proves
IP-level throttling of anonymous traffic, not request spacing. Do not "fix" by
increasing delays. Degrades gracefully — wallstreetbets/investing usually return
posts. A real fix needs Reddit OAuth, which this codebase does not support.

### User is a retail investor seeking profit — measured findings (2026-08-24)
User asked to make this a "world best profit making project" that says when to
buy/sell and picks the best SIP. Position taken: **no buy/sell oracle was built**,
because none can work and a confident-looking one would lose their money. Built
`webui/analytics.py` instead — SIP simulation (XIRR), strategy backtesting with
realistic costs, and risk metrics — so real history answers the questions.

Measured results (all in `INVESTING.md`, do not re-derive):
- NIFTY 10y: buy-and-hold +180.4% vs SMA-cross +32.7% vs RSI +24.3%.
- RELIANCE 10y: buy-and-hold +497.2% vs timing +140.8% / +174.9%.
- TCS 10y: SMA-cross DID beat hold (+141% vs +128%, drawdown -28% vs -53%) —
  the one exception; treat as luck, not edge.
- SIP Rs5k/mo 10y XIRR: RELIANCE 13.03%, ^NSEI 10.38%, HDFCBANK 4.69%, TCS 3.21%.
  The index beat 2 of 3 blue chips.
- NIFTY SIP since 2016 = 10.75% XIRR vs lump sum +212.96%.

**Mutual funds ARE available** (corrects an earlier note): Yahoo carries Indian
MF NAVs under opaque `0P...` codes, e.g. Bandhan Small Cap Dir Gr =
`0P0001J6FU.BO`, 1228 days of history. Search returns no name for them — call
`get_info()` to resolve it (cached in `resolver.fund_name`). `resolver.search(...,
funds=True)` ranks funds first and labels Direct/Regular + Growth/IDCW.
Bonds and FDs are still NOT covered, and expense ratios are not in the data.

### Gemini free-tier daily caps (measured 2026-08-24)
`gemini-3.5-flash` free tier = **20 requests/DAY** — about one analysis run, then
every call 429s with RESOURCE_EXHAUSTED. `gemini-3.1-flash-lite` has a separate,
much larger bucket. `.env` therefore uses flash-lite for BOTH deep and quick.
Switch deep back to `gemini-3.5-flash` only on a paid key.

### Groww API evaluated and rejected (2026-08-24)
User has a Groww account and asked about using its API for history/news. Groww's
Trading API provides OHLC/live quotes/orders for NSE+BSE only, history from 2020,
requires an API-key subscription — and provides **no news and no fundamentals**,
which is most of what the analysts need. Yahoo already covers Indian equities
fully (verified: POWERINDIA.NS = Rs 33,840, full run completed). Integrating
Groww would be a large new vendor for zero gain. Do not revisit unless the goal
becomes *order execution*, which this project does not do.

### No backtesting engine (verified)
`backtrader` is in `pyproject.toml` dependencies but is **never imported in
project source** (grep over `tradingagents/`, `cli/`, `tests/`, `main.py` → zero
hits). "backtest" mentions in the code are look-ahead prevention, not a backtest
loop. Do not go looking for a backtest harness; there isn't one.

### Expect both to be worse on Codespaces
Datacenter IPs are throttled harder than residential.

---

## 5. Changes made to the upstream repo

| File | Change |
|---|---|
| `tradingagents/__init__.py` | Added `_AFCNoticeFilter` to silence the per-call `google_genai.models` AFC warning. Follows the file's existing suppression pattern. |
| `main.py` | Added commented `data_vendors` line to enable Alpha Vantage news fallback once its key is set. |
| `.env` | Created. Google + FRED keys, model config, documented alternatives. |
| `.devcontainer/devcontainer.json` | Created for Codespaces (Python 3.12, auto `pip install '.[dev]'`). |
| `webui/` | **Added.** Local FastAPI dashboard: live run streaming (SSE), results browser, SIP simulator, strategy backtester. New code, no upstream changes. |
| `pyproject.toml` | Added optional `[webui]` extra and included the `webui` package. |
| `RUN_LOCAL.md`, `PROJECT_CONTEXT.md`, `FEATURES.md`, `WEBUI.md`, `TICKERS.md` | Created. Docs only. |

**No upstream bugs were found.** Nothing was patched to make the project work.

---

## 6. Gotchas

1. **`pip install .` copies into site-packages** — source edits then have no
   effect. Now on `pip install -e .`; keep it that way.
2. **PowerShell wraps native stderr** in red `NativeCommandError` blocks. This
   looks like a crash but is not — check the actual exit code.
3. **The AFC filter only applies if `tradingagents` is imported.** A test script
   importing `langchain_google_genai` directly will still show the warning. Not a
   failure.
4. **`get_macro_data(indicator, curr_date)`** — indicator comes first. The
   LangChain tool is `macro_data_tools.get_macro_indicators`, invoked via
   `.invoke({...})`, and is NOT importable from `dataflows.interface`.
5. **`save_reports()` default layout differs from the CLI's.** It writes
   `logs/reports/<TICKER>_<ts>/`; the CLI writes `logs/<TICKER>/<date>/reports/`.
   Pass an explicit `save_path` when you need them in one place.
6. **Only `propagate()` writes the decision log** — not the CLI, not a raw
   `graph.stream()`. Streaming directly means calling `_resolve_pending_entries()`
   and `memory_log.store_decision()` yourself, or runs never reach history and the
   reflection loop stalls.
7. **The report tree names files by role, not section key** — `1_analysts/market.md`,
   `5_portfolio/decision.md`. `webui/history.py:_FILE_KEYS` maps them back.
8. **`resolve_instrument_context()` returns a prompt string, not a dict.** The
   company name is embedded as `Company: <name>;`.
9. **Tickers are symbols, never names.** `safe_ticker_component` enforces
   `^[A-Za-z0-9.^=-]{1,24}$` (no spaces) because tickers become directory names.
   "NIFTY 50" is rejected; `^NSEI` is correct. The **dashboard** accepts free-form
   names via `webui/resolver.py` (resolved / ambiguous / not_found) and asks the
   user when ambiguous; the CLI still needs an exact ticker. Two pre-flight checks
   run before any LLM call: symbol has data, and has data *at the analysis date*
   (post-demerger tickers like TMCV.NS trade today but not in 2024). See `TICKERS.md`.
10. **Reasoning models ignore `temperature`.** Runs are non-deterministic by
   design; this is documented upstream, not a defect.

---

## 7. Baselines

- **Test suite: 576 passed, 2 skipped, 0 failed** (~105s). Stable before and
  after all changes. The 2 skips are optional `langchain-aws` and a live DeepSeek
  call — both expected.
- **Full pipeline runs: 2/2 exit 0.** NVDA @ 2024-05-10 → **BUY** both times
  (run 1: Overweight, entry $88.50/stop $86.00; run 2: Buy, scaled entry, stop
  $84.00 widened for ATR). Target $93.88, 3–6mo horizon in both.
- **Warning counts in run 2: AFC 0, FRED 0, tracebacks 0.** StockTwits (1) and
  Reddit (2) still fail as expected — unfixable, see section 4.
- **FRED confirmed end-to-end, not silently skipped.** Run 2 log shows
  `get_macro_indicators (call_...) indicator: cpi` and the real values
  (CPI 313.175, Fed Funds 5.33%) flowing into the news report. Note: grepping the
  log for `## FRED:` returns 0 because the analyst reformats rather than echoing
  the raw header — grep for the tool call or the values instead.
- **The reflection/memory loop works.** Run 2 fetched run 1's realised return
  (+1.2% alpha), wrote a reflection, and run 2's thesis explicitly cites it
  ("our prior reflections show that structural momentum often overrides technical
  mean-reversion"). Decision log: `~/.tradingagents/memory/trading_memory.md`.

---

## 8. Open / next steps

- [ ] Optional: add `ALPHA_VANTAGE_API_KEY` (only remaining empty key), then uncomment the `data_vendors`
      line in `main.py` for real news sentiment (best free replacement for the
      dead StockTwits + throttled Reddit feeds).
- [ ] Push to a GitHub repo and open a Codespace (devcontainer is ready).
      Free tier: 120 core-hours/mo (≈60h on 2-core), 15 GB storage. Blocked, not
      charged, at quota. Add the key as a Codespaces Secret.
- [ ] Vercel was considered and **rejected**: interactive TUI with no HTTP
      server, multi-minute runs vs 60–300s function cap, ephemeral filesystem vs
      SQLite checkpoints. Do not revisit.
