# TradingAgents — setup, run guide, and warning status

## 1. How to run

Open PowerShell, `cd` to the project once, then pick what you want:

```powershell
cd D:\git\trading\TradingAgents
```

### A) Web dashboard — the main way to use this

```powershell
.\.venv\Scripts\python.exe -m webui
```

Opens <http://localhost:8000> in your browser automatically. Everything lives
here: run an AI analysis and watch each agent finish live, the SIP simulator,
the strategy backtester, market data, and past decisions. Stop it with `Ctrl+C`.

### B) Interactive CLI — same analysis, in the terminal

```powershell
.\.venv\Scripts	radingagents.exe
```

Menu-driven: pick ticker, date, analysts and depth. Needs an exact ticker
(`RELIANCE.NS`), not a name — only the dashboard resolves names.

### C) Scripted single run — for automation

```powershell
.\.venv\Scripts\python.exe main.py
```

Edit the ticker and date inside `main.py` first.

### D) Evidence tools only — no LLM, no API key used

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.index:app --port 8010
```

Serves <http://localhost:8010> with just the SIP simulator and backtester. This
is the exact app Vercel runs, so use it to check the hosted version locally.

### E) Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

There is no "activate the venv" step needed — calling `.\.venv\Scripts\...`
directly uses the right interpreter. If you prefer activating:

```powershell
.\.venv\Scripts\Activate.ps1
tradingagents
```

If PowerShell blocks the activate script, use the direct-path form above instead
(it needs no execution-policy change, so no admin).

### Useful flags

```powershell
.\.venv\Scripts\tradingagents.exe --checkpoint          # resume if a run crashes
.\.venv\Scripts\tradingagents.exe --clear-checkpoints   # reset saved state first
.\.venv\Scripts\tradingagents.exe --help
```

### Changing what gets analysed

- **CLI (A)** prompts you for ticker and date each run.
- **Script (B)**: edit the last lines of `main.py` — `ta.propagate("NVDA", "2024-05-10")`.
- **Models / rounds**: edit `.env` (`TRADINGAGENTS_*` keys) — no code change needed.

Tickers use Yahoo suffixes: `AAPL`, `RELIANCE.NS`, `0700.HK`, `7203.T`, `BTC-USD`.

### Where output goes

- Reports stream to the terminal as each agent finishes.
- Decision log appends to `~/.tradingagents/memory/trading_memory.md`, so the next
  run on the same ticker reflects on how the previous call turned out.

## 2. Status of the four warnings

| # | Warning | Fixable? | What was done |
|---|---|---|---|
| 1 | `AFC not recommended` | **Yes — fixed** | Filtered in code. Gone. |
| 2 | `FRED_API_KEY not set` | **Yes — FIXED** | Key added and verified live (real CPI/FEDFUNDS data) |
| 3 | `Reddit RSS 429` | **No** | Not a pacing bug — see below |
| 4 | `StockTwits 403` | **No free fix** | API is now OAuth-only — see below |

### 1. AFC notice — fixed

`google-genai` logs this on every call because LangChain uses the stateless
`generate_content` path deliberately. A targeted filter in
`tradingagents/__init__.py` drops that one message and leaves all other
`google_genai.models` logs intact. Verified silent.

### 2. FRED — fixed

Key is set in `.env` and verified with live calls: `get_macro_indicators` now
returns real CPI and Federal Funds Rate series through the vendor router. The
macro warning is gone and the news analyst has real macro data to ground on.

### 3. Reddit 429 — not fixable from here

I tested this rather than guessing. The fetcher already paces requests at 1s and
backs off on 429. **Raising the delay to 4s made it worse** — two subreddits
failed instead of one — which proves it is IP-level throttling of anonymous
traffic, not a request-spacing bug. Increasing delays or spoofing headers would
not fix it, so I changed nothing.

It also degrades gracefully: `r/wallstreetbets` and `r/investing` returned real
posts; only `r/stocks` failed. A proper fix needs Reddit OAuth app credentials,
which this codebase does not currently support.

### 4. StockTwits 403 — no free path

I tested both the project's own User-Agent and a browser User-Agent. **Both got
403.** StockTwits has closed their formerly keyless public API; it now requires
OAuth. This is not something a code change can work around, and I did not attempt
to evade their block.

### Best available replacement for 3 and 4

**Alpha Vantage** — free tier, 25 requests/day, no card:
https://www.alphavantage.co/support/#api-key

Its `NEWS_SENTIMENT` endpoint returns genuine sentiment scores and is already
implemented in this project. Paste the key into `.env`, then uncomment the
`data_vendors` line in `main.py` to add it as a fallback behind yfinance.

This does not restore social-media chatter, but it does restore a real sentiment
signal, which is what those two sources were feeding.

## 3. What was installed

| Item | Location | Admin needed? |
|---|---|---|
| Python 3.12.10 | `%LOCALAPPDATA%\Programs\Python\Python312` | **No** — per-user |
| Virtualenv | `.venv\` in the project | No |
| `tradingagents` 0.3.1 | editable install (`pip install -e .`) | No |

The install is **editable**, so edits to the source tree take effect immediately
with no reinstall.

## 4. Verification performed

- `pytest` → **576 passed, 2 skipped, 0 failed** (before and after my changes)
- Live Gemini call on both configured models → OK
- Full `main.py` run → **exit 0**, decision **BUY / Overweight**
  (entry $88.50, stop $86.00, target $93.88), decision log written

## 5. GitHub Codespaces

`.devcontainer/devcontainer.json` is included; Codespaces auto-builds Python 3.12
and installs the project on create.

| Plan | Compute | Storage |
|---|---|---|
| GitHub Free | 120 core-hours/month | 15 GB-month |
| GitHub Pro | 180 core-hours/month | 20 GB-month |

Core-hours bill **per core**: a 2-core machine burns 2 per wall-clock hour, so
120 core-hours ≈ **60 real hours/month**. With no card on file, usage is blocked
at the quota rather than charged. Stop the Codespace when idle.

**Put your API key in Codespaces Secrets** (repo → Settings → Secrets and
variables → Codespaces), never in a committed `.env`. `.env` is gitignored here.

Note: the StockTwits/Reddit blocks will likely be **worse** on Codespaces, since
datacenter IPs are throttled more aggressively than home connections.
