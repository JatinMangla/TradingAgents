"""FastAPI server for the TradingAgents dashboard.

Endpoints
---------
``GET  /``                     the single-page dashboard
``POST /api/run``              start an analysis (one at a time)
``GET  /api/run/{id}``         snapshot of a run
``GET  /api/run/{id}/stream``  Server-Sent Events: live agent progress
``GET  /api/history``          past decisions from the decision log
``GET  /api/history/{t}/{d}``  saved report sections for one run
``GET  /api/market/{ticker}``  live price, indicators and macro
``GET  /api/config``           provider/model/key status for the header

Deliberately single-process and in-memory: this is a local research dashboard,
not a multi-user service.
"""

from __future__ import annotations

import json
import logging
import os
import queue
from datetime import date as _date
from datetime import timedelta as _timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

import tradingagents  # noqa: F401  - loads .env and installs log filters
from tradingagents.default_config import DEFAULT_CONFIG
from webui import analytics, history, resolver
from webui.run_manager import MANAGER

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="TradingAgents Dashboard", docs_url="/api/docs")


class RunRequest(BaseModel):
    # Longer than a ticker: this field accepts free-form names too.
    ticker: str = Field(min_length=1, max_length=120)
    date: str = Field(default_factory=lambda: _date.today().isoformat())
    analysts: list[str] = Field(default_factory=lambda: ["market", "social", "news", "fundamentals"])
    # Set when the value came from the chooser, so we don't re-resolve it.
    resolved: bool = False


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
def get_config() -> dict:
    """What the run will use, plus which optional keys are present.

    Only booleans are returned for keys — never the values themselves.
    """
    return {
        "provider": DEFAULT_CONFIG.get("llm_provider"),
        "deep_think_llm": DEFAULT_CONFIG.get("deep_think_llm"),
        "quick_think_llm": DEFAULT_CONFIG.get("quick_think_llm"),
        "max_debate_rounds": DEFAULT_CONFIG.get("max_debate_rounds"),
        "max_risk_rounds": DEFAULT_CONFIG.get("max_risk_rounds"),
        "keys": {
            "google": bool(os.getenv("GOOGLE_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "fred": bool(os.getenv("FRED_API_KEY")),
            "alpha_vantage": bool(os.getenv("ALPHA_VANTAGE_API_KEY")),
        },
    }


@app.post("/api/run")
def start_run(req: RunRequest) -> dict:
    """Start a run, or ask the user which instrument they meant.

    The ticker field accepts anything — a symbol, a company name, an index name.
    When the input resolves to exactly one runnable instrument we start; when it
    is ambiguous we return candidates instead of guessing, because silently
    analysing the wrong company is far worse than one extra click.
    """
    # An explicit pick from the chooser skips resolution entirely.
    if req.resolved:
        symbol = req.ticker.strip().upper()
        if not resolver.is_path_safe(symbol):
            raise HTTPException(status_code=400, detail=f"'{req.ticker}' is not a usable ticker.")
        return _launch(symbol, req)

    outcome = resolver.resolve(req.ticker)

    if outcome["status"] == "resolved":
        return _launch(outcome["symbol"], req)

    if outcome["status"] == "ambiguous":
        return {
            "status": "needs_selection",
            "query": req.ticker,
            "message": f"Several instruments match “{req.ticker}”. Which did you mean?",
            "candidates": outcome["candidates"],
        }

    return {
        "status": "not_found",
        "query": req.ticker,
        "message": (
            f"Nothing tradable matched “{req.ticker}”. Try the company's full name, "
            f"or a ticker such as RELIANCE.NS (NSE), POWERINDIA.BO (BSE), "
            f"^NSEI (NIFTY 50) or AAPL."
        ),
        "candidates": [],
    }


def _launch(symbol: str, req: RunRequest) -> dict:
    # The symbol may trade today yet not exist at the requested analysis date
    # (recent listings, post-demerger tickers). Catch that here rather than
    # failing minutes into the run.
    if not resolver.has_data_on(symbol, req.date):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{symbol} has no price history around {req.date}. It may have "
                f"listed later than that date. Pick a more recent analysis date, "
                f"or choose the pre-existing listing for this company."
            ),
        )

    try:
        run = MANAGER.start(symbol, req.date, req.analysts)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    snap = run.snapshot()
    snap["status_kind"] = "started"
    return snap


@app.get("/api/resolve")
def resolve_ticker(q: str) -> dict:
    """Resolve free-form text to a ticker, or return the choices."""
    return resolver.resolve(q)


@app.get("/api/run/{run_id}")
def get_run(run_id: str) -> dict:
    run = MANAGER.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="unknown run")
    return run.snapshot()


@app.get("/api/run/{run_id}/stream")
def stream_run(run_id: str) -> StreamingResponse:
    run = MANAGER.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="unknown run")

    def gen():
        # Replay what already happened so a reconnecting browser is not left
        # with a blank timeline mid-run.
        for evt in run.replay():
            yield f"data: {json.dumps(evt)}\n\n"
        if run.status in ("done", "error"):
            yield 'data: {"kind": "eof"}\n\n'
            return
        while True:
            try:
                evt = run.q.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"   # keeps proxies from closing the stream
                continue
            yield f"data: {json.dumps(evt)}\n\n"
            if evt.get("kind") == "eof":
                return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/history")
def get_history() -> dict:
    return {"runs": history.list_runs()}


@app.get("/api/history/{ticker}/{run_date}")
def get_history_reports(ticker: str, run_date: str) -> dict:
    # Both values land in a filesystem path, so refuse anything with separators
    # or traversal before touching disk.
    for value in (ticker, run_date):
        if not value or "/" in value or "\\" in value or ".." in value:
            raise HTTPException(status_code=400, detail="invalid ticker or date")
    return {"sections": history.reports_for(ticker, run_date)}


@app.get("/api/search")
def search_tickers(q: str, limit: int = 8) -> dict:
    """Resolve a company or index *name* to Yahoo ticker symbols.

    The analysis pipeline needs a ticker (``^NSEI``), not a name ("nifty 50"),
    so the dashboard uses this to turn what people naturally type into something
    the graph can actually run.
    """
    return {"results": resolver.search(q, limit=max(1, min(limit, 15)))}


@app.get("/api/sip")
def sip(ticker: str, monthly: float = 5000, years: int = 10) -> dict:
    """Simulate a real monthly SIP over actual prices."""
    if not resolver.is_path_safe(ticker):
        raise HTTPException(status_code=400, detail="invalid ticker")
    if monthly <= 0 or years < 1 or years > 30:
        raise HTTPException(status_code=400, detail="monthly must be > 0 and years 1-30")

    end = _date.today()
    start = end - _timedelta(days=int(years * 365.25))
    try:
        return analytics.simulate_sip(ticker, monthly, start.isoformat(), end.isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sip/search")
def sip_search(q: str, limit: int = 8) -> dict:
    """Find funds, ETFs and indices by name, for the SIP tool.

    Ranks mutual funds first and resolves Yahoo's opaque fund codes
    (``0P0001J6FU.BO``) to readable scheme names.
    """
    return {"results": resolver.search(q, limit=max(1, min(limit, 12)), funds=True)}


@app.get("/api/sip/compare")
def sip_compare(tickers: str, monthly: float = 5000, years: int = 10) -> dict:
    """Rank several instruments by the XIRR the same SIP would have produced."""
    names = [t.strip() for t in tickers.split(",") if t.strip()][:8]
    if not names:
        raise HTTPException(status_code=400, detail="no tickers given")
    if monthly <= 0 or years < 1 or years > 30:
        raise HTTPException(status_code=400, detail="monthly must be > 0 and years 1-30")

    # Entries may be fund names ("bandhan small cap"), not symbols. Resolve each;
    # stop and ask as soon as one is ambiguous, so the user picks the exact share
    # class rather than us guessing between Direct/Regular and Growth/IDCW.
    resolved: list[str] = []
    for name in names:
        if resolver.is_path_safe(name) and resolver.has_market_data(name):
            resolved.append(name)
            continue
        candidates = resolver.search(name, limit=8, funds=True)
        if not candidates:
            return {
                "status": "not_found", "query": name,
                "message": (
                    f"Nothing matched “{name}”. Check the spelling, or search the "
                    f"fund house name (e.g. “bandhan small cap”, “parag parikh flexi”)."
                ),
                "candidates": [],
            }
        return {
            "status": "needs_selection", "query": name,
            "message": f"Which “{name}”? Direct + Growth is usually the right choice for a long SIP.",
            "candidates": candidates,
        }

    return analytics.compare_sip(resolved, monthly, years)


@app.get("/api/backtest")
def backtest(ticker: str, years: int = 10) -> dict:
    """Compare timing strategies against buy-and-hold and the index."""
    if not resolver.is_path_safe(ticker):
        raise HTTPException(status_code=400, detail="invalid ticker")
    if years < 1 or years > 30:
        raise HTTPException(status_code=400, detail="years must be 1-30")

    end = _date.today()
    start = end - _timedelta(days=int(years * 365.25))
    try:
        return analytics.backtest(ticker, start.isoformat(), end.isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/market/{ticker}")
def get_market(ticker: str, period: str = "6mo") -> dict:
    """Recent OHLCV plus the indicators the Market Analyst uses, and key macro.

    Used by the dashboard's market panel. Degrades field-by-field: a failure in
    indicators or macro still returns prices.
    """
    if not ticker or "/" in ticker or "\\" in ticker or ".." in ticker:
        raise HTTPException(status_code=400, detail="invalid ticker")
    if period not in {"1mo", "3mo", "6mo", "1y", "2y"}:
        raise HTTPException(status_code=400, detail="invalid period")

    import pandas as pd
    import yfinance as yf

    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    except Exception as exc:                       # noqa: BLE001 - upstream/network
        raise HTTPException(status_code=502, detail=f"price fetch failed: {exc}") from exc

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"no price data for {ticker}")

    df = df.reset_index()
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    dates = [str(pd.Timestamp(d).date()) for d in df[date_col]]
    close = [round(float(c), 4) for c in df["Close"]]
    volume = [int(v) if pd.notna(v) else 0 for v in df.get("Volume", [])]

    latest, prev = close[-1], (close[-2] if len(close) > 1 else close[-1])
    change = latest - prev
    pct = (change / prev * 100) if prev else 0.0

    indicators = _safe_indicators(df)
    macro = _safe_macro()

    return {
        "ticker": ticker.upper(),
        "period": period,
        "dates": dates,
        "close": close,
        "volume": volume,
        "latest": round(latest, 4),
        "change": round(change, 4),
        "change_pct": round(pct, 2),
        "high_52w": round(float(df["Close"].max()), 4),
        "low_52w": round(float(df["Close"].min()), 4),
        "indicators": indicators,
        "macro": macro,
    }


def _safe_indicators(df) -> dict:
    """MACD / RSI / Bollinger / ATR / VWMA via stockstats; {} if it fails."""
    try:
        from stockstats import wrap

        frame = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].copy()
        sdf = wrap(frame)
        wanted = {
            "rsi": "rsi_14",
            "macd": "macd",
            "atr": "atr_14",
            "boll_ub": "boll_ub",
            "boll_lb": "boll_lb",
            "close_50_sma": "close_50_sma",
            "close_200_sma": "close_200_sma",
        }
        out: dict[str, float | None] = {}
        for label, col in wanted.items():
            try:
                series = sdf[col].dropna()
                out[label] = round(float(series.iloc[-1]), 4) if len(series) else None
            except Exception:                       # noqa: BLE001 - per-indicator
                out[label] = None
        # Full SMA lines for the chart, aligned to the price series length.
        for col in ("close_50_sma", "close_200_sma"):
            try:
                out[f"{col}_series"] = [
                    None if v != v else round(float(v), 4) for v in sdf[col]
                ]
            except Exception:                       # noqa: BLE001
                out[f"{col}_series"] = []
        return out
    except Exception as exc:                        # noqa: BLE001 - optional panel
        logger.warning("indicator computation failed: %s", exc)
        return {}


def _trim_number(value: str) -> str:
    """FRED returns padded decimals like '3.6300000000'; show '3.63'."""
    try:
        return f"{float(value):g}"
    except ValueError:
        return value


def _safe_macro() -> list[dict]:
    """A few headline FRED series; empty list when no key is configured."""
    if not os.getenv("FRED_API_KEY"):
        return []
    from tradingagents.dataflows.fred import get_macro_data

    today = _date.today().isoformat()
    out = []
    for key, label in (("cpi", "CPI"), ("fed_funds_rate", "Fed Funds"),
                       ("unemployment", "Unemployment"), ("10y_treasury", "10Y Treasury")):
        try:
            text = get_macro_data(key, today)
            value, as_of = "", ""
            for line in text.splitlines():
                if line.startswith("**Latest:**"):
                    body = line.split("**Latest:**", 1)[1].strip()
                    value = body.split("|")[0].strip()
                    if "(" in value:
                        value, as_of = value.split("(", 1)[0].strip(), value.split("(", 1)[1].rstrip(")")
                    break
            if value:
                out.append({
                    "key": key, "label": label,
                    "value": _trim_number(value), "as_of": as_of,
                })
        except Exception as exc:                    # noqa: BLE001 - optional panel
            logger.warning("macro %s failed: %s", key, exc)
    return out
