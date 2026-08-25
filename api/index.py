"""Vercel serverless entry point — the evidence tools only.

What this deploys
-----------------
The SIP simulator, the strategy backtester, the market panel, and instrument
search. All are fast, stateless HTTP calls over public price data, which is
exactly what serverless is good at.

What this deliberately does NOT deploy, and why
-----------------------------------------------
The multi-agent LLM pipeline. It is not a config problem — three properties of
the platform make it unworkable:

* **Duration.** One analysis chains many LLM calls and takes minutes. Vercel
  functions cap at 60s on Hobby and 300s on Pro, so a run gets killed partway.
* **Streaming.** The dashboard's live agent-by-agent progress is Server-Sent
  Events held open for the length of a run. Serverless functions do not hold
  connections like that.
* **Persistence.** The decision log, the reflection loop that scores past calls,
  the checkpoints, and the saved reports are all files under ``~/.tradingagents``.
  A serverless filesystem is ephemeral, so every one of those writes would be
  discarded between requests — the learning loop would silently never work.

Run the agent pipeline locally (``python -m webui``) or on a always-on host.
See ``DEPLOY.md``.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

# The repo root holds the `webui` package; Vercel runs this file from `api/`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webui import analytics, resolver  # noqa: E402

app = FastAPI(title="Investing Evidence Tools", docs_url="/api/docs")

_STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = _STATIC / "cloud.html"
    if page.exists():
        return page.read_text(encoding="utf-8")
    return "<h1>Investing Evidence Tools</h1><p>See <a href='/api/docs'>/api/docs</a>.</p>"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": "serverless", "tools": ["sip", "backtest", "market", "search"]}


def _guard(ticker: str) -> None:
    if not resolver.is_path_safe(ticker):
        raise HTTPException(status_code=400, detail=f"invalid ticker: {ticker}")


def _window(years: int) -> tuple[str, str]:
    end = date.today()
    return (end - timedelta(days=int(years * 365.25))).isoformat(), end.isoformat()


@app.get("/api/search")
def search(q: str, limit: int = 8, funds: bool = False) -> dict:
    return {"results": resolver.search(q, limit=max(1, min(limit, 12)), funds=funds)}


@app.get("/api/sip/search")
def sip_search(q: str, limit: int = 8) -> dict:
    return {"results": resolver.search(q, limit=max(1, min(limit, 12)), funds=True)}


@app.get("/api/sip/compare")
def sip_compare(tickers: str, monthly: float = 5000, years: int = 10) -> dict:
    names = [t.strip() for t in tickers.split(",") if t.strip()][:6]
    if not names:
        raise HTTPException(status_code=400, detail="no instruments given")
    if monthly <= 0 or not 1 <= years <= 30:
        raise HTTPException(status_code=400, detail="monthly must be > 0 and years 1-30")

    resolved: list[str] = []
    for name in names:
        if resolver.is_path_safe(name) and resolver.has_market_data(name):
            resolved.append(name)
            continue
        candidates = resolver.search(name, limit=8, funds=True)
        if not candidates:
            return {"status": "not_found", "query": name, "candidates": [],
                    "message": f"Nothing matched “{name}”. Check the spelling, or try the fund house name."}
        return {"status": "needs_selection", "query": name, "candidates": candidates,
                "message": f"Which “{name}”? Direct + Growth is usually right for a long SIP."}

    return analytics.compare_sip(resolved, monthly, years)


@app.get("/api/backtest")
def backtest(ticker: str, years: int = 10) -> dict:
    _guard(ticker)
    if not 1 <= years <= 30:
        raise HTTPException(status_code=400, detail="years must be 1-30")
    start, end = _window(years)
    try:
        return analytics.backtest(ticker, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/market/{ticker}")
def market(ticker: str, period: str = "6mo") -> dict:
    """Recent prices plus the indicators the dashboard's market panel shows."""
    _guard(ticker)
    if period not in {"1mo", "3mo", "6mo", "1y", "2y"}:
        raise HTTPException(status_code=400, detail="invalid period")

    import pandas as pd
    import yfinance as yf

    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    except Exception as exc:  # noqa: BLE001 - upstream/network
        raise HTTPException(status_code=502, detail=f"price fetch failed: {exc}") from exc
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"no price data for {ticker}")

    df = df.reset_index()
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    close = [round(float(c), 4) for c in df["Close"]]
    latest = close[-1]
    prev = close[-2] if len(close) > 1 else latest
    return {
        "ticker": ticker.upper(),
        "dates": [str(pd.Timestamp(d).date()) for d in df[date_col]],
        "close": close,
        "latest": round(latest, 4),
        "change": round(latest - prev, 4),
        "change_pct": round((latest - prev) / prev * 100, 2) if prev else 0.0,
        "high": round(float(df["Close"].max()), 4),
        "low": round(float(df["Close"].min()), 4),
        "indicators": analytics.indicators_for(df),
    }
