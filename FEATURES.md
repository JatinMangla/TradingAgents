# TradingAgents — capabilities reference

Derived by reading the v0.3.1 source, not just the README. Verified claims are
marked; gaps are called out honestly.

---

## 1. The core idea

It simulates a **trading firm as a multi-agent LLM debate**. A ticker + date goes
in; a structured investment decision comes out. Built on **LangGraph** — agents
are graph nodes with real state, conditional routing, and checkpointing.

It is a **research scaffold**, not a trading bot. It places no orders and
connects to no broker.

---

## 2. The agent roster (12 agents, 5 stages)

**Stage 1 — Analysts** (user-selectable; run in parallel)
| Agent | Does |
|---|---|
| Market/Technical | Picks ≤8 complementary indicators, reads price action |
| Fundamentals | Financials, ratios, insider transactions |
| News | Company + global news, macro indicators, prediction markets |
| Sentiment | StockTwits + Reddit → single sentiment read *(sources degraded — §7)* |
| Social Media | Separate social-focused variant |

**Stage 2 — Researchers:** Bull vs Bear structured debate, N configurable rounds.

**Stage 3 — Research Manager:** adjudicates the debate into a `ResearchPlan`.

**Stage 4 — Trader:** produces a `TraderProposal` — action, entry price, stop
loss, position sizing, reasoning.

**Stage 5 — Risk team:** Aggressive / Conservative / Neutral debators argue the
proposal, then the **Portfolio Manager** issues the final `PortfolioDecision`.

Ratings use a five-tier scale: **Buy · Overweight · Hold · Underweight · Sell**.

---

## 3. Data capabilities

**12 tools** are exposed to the agents:
`get_stock_data`, `get_indicators`, `get_fundamentals`, `get_balance_sheet`,
`get_cashflow`, `get_income_statement`, `get_news`, `get_global_news`,
`get_insider_transactions`, `get_macro_indicators`, `get_prediction_markets`,
`get_verified_market_snapshot`.

**Technical indicators (12):** `close_50_sma`, `close_200_sma`, `close_10_ema`,
`macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`.

**Macro via FRED (28 series):** rates (fed funds, 2y/10y/30y treasury, yield
curve, 10y-2y spread), inflation (CPI, core CPI, PCE, core PCE, expectations),
labor (unemployment, nonfarm payrolls, initial claims), growth (GDP, real GDP,
industrial production, retail sales, housing starts), and market/liquidity
(VIX, M2, dollar index, consumer sentiment). *Verified working.*

**Prediction markets:** Polymarket, keyless — live market-implied probabilities
for forward-looking events, filtered to genuinely forward-looking markets.

**Vendor routing:** each data category has a configurable vendor chain with
ordered fallback, e.g. `"news_data": "yfinance,alpha_vantage"`. Requests are
never silently routed to vendors you did not choose.

---

## 4. Market coverage

Any market Yahoo Finance covers, via exchange suffix. Company identity and the
alpha benchmark resolve **automatically per market**:

| Market | Ticker | Auto benchmark |
|---|---|---|
| US | `AAPL` | SPY |
| India | `RELIANCE.NS` / `.BO` | Nifty 50 / Sensex |
| Japan | `7203.T` | Nikkei 225 |
| Hong Kong | `0700.HK` | Hang Seng |
| UK | `AZN.L` | FTSE 100 |
| Canada / Australia | `.TO` / `.AX` | TSX / ASX 200 |
| China A-shares | `600519.SS` / `.SZ` | SSE / SZSE |
| Crypto | `BTC-USD` | — |

---

## 5. LLM provider support — 18 providers

`openai`, `anthropic`, `google`, `xai`, `deepseek`, `qwen` (+`qwen-cn`),
`glm` (+`glm-cn`), `minimax` (+`minimax-cn`), `kimi`, `mistral`, `groq`,
`nvidia`, `bedrock`, `ollama`, `openai_compatible`.

- **Two-tier models:** a "deep think" model for reasoning-heavy nodes and a
  cheaper "quick think" model for the rest.
- `openai_compatible` covers vLLM / LM Studio / llama.cpp / any relay.
- `ollama` runs fully local with **no API key**.
- Provider-specific reasoning depth controls (OpenAI effort, Google thinking
  level, Anthropic effort).
- Configurable retry budget to ride out 429 throttling.

---

## 6. Notable engineering features

**Memory & reflection (the standout feature).** Every completed run appends to
`~/.tradingagents/memory/trading_memory.md`. On the next run for that ticker it
fetches the **realised return (raw and alpha vs the right benchmark)**, writes a
reflection, and injects prior decisions into the Portfolio Manager prompt.
*Verified: run 2 picked up run 1's +1.2% alpha and explicitly changed its stop-loss
because of it.*

**Checkpoint resume** (`--checkpoint`). LangGraph saves state per node into
per-ticker SQLite at `~/.tradingagents/cache/checkpoints/<TICKER>.db`, so a
crashed run resumes instead of restarting. Graph-shape-aware.

**Anti-hallucination measures** — the most interesting part of v0.3.x:
- `get_verified_market_snapshot` is the designated source of truth; agents must
  flag conflicts rather than inventing reconciled numbers.
- Ticker identity is resolved **deterministically before any agent runs**, fixing
  earlier "analysed the wrong company" bugs.
- Alpha Vantage look-ahead filtering and news date fidelity — agents cannot see
  data published after the analysis date.

**Structured outputs.** Pydantic schemas (`ResearchPlan`, `TraderProposal`,
`PortfolioDecision`, `SentimentReport`) — typed fields with confidence bands, not
free text to regex.

**Multi-language output** via `TRADINGAGENTS_OUTPUT_LANGUAGE` — applied to every
agent so reports are fully localized, and costing zero extra tokens in English.

**Rich terminal UI** — live agent progress, streaming reports, token counters.

**Config without code edits** — any `TRADINGAGENTS_*` env var overrides the
matching `DEFAULT_CONFIG` key, type-coerced. Docker and devcontainer included.

---

## 7. Honest limitations

**No backtesting engine for the agents.** (`backtrader` was declared but never
imported; it was removed as a dependency on 2026-09-29.) The dashboard's
backtester covers simple rule-based strategies only. The "backtest" references in the code are about look-ahead
prevention, not a backtest loop. There is no portfolio simulation, no P&L curve,
no walk-forward harness. Treat single-date analysis as the actual scope.

**No broker integration.** Nothing executes. The "simulated exchange" in the
README's diagram is not a component you can point at an account.

**Two sentiment sources are degraded** (measured on this machine):
- StockTwits → **403**, their public API is OAuth-only now.
- Reddit → **429**, IP-level throttling of anonymous RSS.

The Sentiment Analyst still runs but on thinner input, and it is instructed to
flag reduced confidence when sources return placeholders. Alpha Vantage
`NEWS_SENTIMENT` (free key) is the best available substitute.

**Non-deterministic by design.** Two runs of the same ticker/date can differ —
LLM sampling plus live news/social data. Upstream documents this as expected, not
a defect. Reasoning models largely ignore `temperature`.

**Not financial advice** — the authors state it is for research only.
