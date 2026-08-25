"""Evidence tools: SIP simulation, strategy backtesting, and risk metrics.

Why this module exists
----------------------
The agent pipeline produces an *opinion*. An opinion cannot tell you whether a
strategy makes money — only history can, and only with its losses shown next to
its gains. Everything here is arithmetic over real price data: no model, no
forecast, no prediction.

Three questions it answers honestly:

* **"Should I SIP?"** — :func:`simulate_sip` runs a real monthly-investment
  schedule over actual prices and reports XIRR, not a marketing CAGR.
* **"Does this timing strategy beat just holding?"** — :func:`backtest` runs a
  rule over history and always reports buy-and-hold beside it, because a
  strategy that trails buy-and-hold is a losing strategy however good its chart
  looks.
* **"What could I lose?"** — every result carries max drawdown and volatility,
  since return without risk is half the picture.

Costs are modelled, not ignored: brokerage and slippage are charged on every
simulated trade, which is what usually turns a promising backtest into a
losing one.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
# Round-trip cost assumption per trade, as a fraction of trade value.
# 0.1% is a realistic retail discount-brokerage + slippage figure for delivery
# trades; high-frequency rules get punished by it, which is the point.
DEFAULT_COST = 0.001


# ─────────────────────────────────────────────────────────── data

def load_prices(ticker: str, start: str, end: str):
    """Daily close series for ``ticker``. Raises ValueError when empty."""
    import yfinance as yf

    df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"No price history for {ticker} between {start} and {end}")
    series = df["Close"].dropna()
    if series.empty:
        raise ValueError(f"No usable closes for {ticker}")
    return series


# Same mapping as tradingagents' DEFAULT_CONFIG, duplicated so this module runs
# without the agent stack installed (the serverless deploy ships analytics only).
_FALLBACK_BENCHMARKS = {
    ".NS": "^NSEI", ".BO": "^BSESN", ".T": "^N225", ".HK": "^HSI",
    ".L": "^FTSE", ".TO": "^GSPTSE", ".AX": "^AXJO",
    ".SS": "000001.SS", ".SZ": "399001.SZ", "": "SPY",
}


def indicators_for(df) -> dict:
    """Latest MACD / RSI / ATR / Bollinger / SMA values plus SMA lines.

    Shared by the local dashboard and the serverless deployment so both market
    panels show the same numbers. Degrades per-indicator: one that cannot be
    computed comes back as None rather than failing the whole panel.
    """
    try:
        from stockstats import wrap

        frame = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].copy()
        sdf = wrap(frame)
        wanted = {
            "rsi": "rsi_14", "macd": "macd", "atr": "atr_14",
            "boll_ub": "boll_ub", "boll_lb": "boll_lb",
            "close_50_sma": "close_50_sma", "close_200_sma": "close_200_sma",
        }
        out: dict = {}
        for label, col in wanted.items():
            try:
                series = sdf[col].dropna()
                out[label] = round(float(series.iloc[-1]), 4) if len(series) else None
            except Exception:  # noqa: BLE001 - per-indicator
                out[label] = None
        for col in ("close_50_sma", "close_200_sma"):
            try:
                out[f"{col}_series"] = [None if v != v else round(float(v), 4) for v in sdf[col]]
            except Exception:  # noqa: BLE001
                out[f"{col}_series"] = []
        return out
    except Exception as exc:  # noqa: BLE001 - optional panel
        logger.warning("indicator computation failed: %s", exc)
        return {}


def benchmark_for(ticker: str) -> str:
    """The index this ticker should be judged against, by exchange suffix."""
    try:
        from tradingagents.default_config import DEFAULT_CONFIG

        mapping = DEFAULT_CONFIG.get("benchmark_map", _FALLBACK_BENCHMARKS)
    except ImportError:
        mapping = _FALLBACK_BENCHMARKS

    for suffix, index in mapping.items():
        if suffix and ticker.upper().endswith(suffix.upper()):
            return index
    return mapping.get("", "SPY")


# ─────────────────────────────────────────────────────── risk maths

def _max_drawdown(values: list[float]) -> float:
    """Worst peak-to-trough fall, as a negative fraction."""
    peak, worst = -math.inf, 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1.0)
    return worst


def _cagr(start_value: float, end_value: float, years: float) -> float:
    if start_value <= 0 or years <= 0:
        return 0.0
    return (end_value / start_value) ** (1.0 / years) - 1.0


def _daily_returns(values: list[float]) -> list[float]:
    return [
        values[i] / values[i - 1] - 1.0
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]


def _stats(values: list[float], years: float) -> dict:
    """CAGR, volatility, Sharpe, max drawdown for an equity curve."""
    if len(values) < 2:
        return {"cagr": 0.0, "volatility": 0.0, "sharpe": 0.0,
                "max_drawdown": 0.0, "total_return": 0.0}

    rets = _daily_returns(values)
    mean = sum(rets) / len(rets) if rets else 0.0
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    vol = math.sqrt(var) * math.sqrt(TRADING_DAYS)
    cagr = _cagr(values[0], values[-1], years)
    # Excess return over cash is omitted deliberately: risk-free rates differ by
    # market and would need another data source. This is a comparison tool, and
    # the same simplification applies to every series being compared.
    sharpe = (cagr / vol) if vol > 1e-9 else 0.0
    return {
        "cagr": round(cagr, 4),
        "volatility": round(vol, 4),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(_max_drawdown(values), 4),
        "total_return": round(values[-1] / values[0] - 1.0, 4),
    }


# ──────────────────────────────────────────────────────────── XIRR

def xirr(cashflows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    """Annualised return for irregular cashflows (Newton, bisection fallback).

    SIP contributions arrive monthly, so a plain CAGR would be wrong — money
    invested last month has not had a year to compound. XIRR is the honest
    number, and it is what fund factsheets should quote.
    """
    if len(cashflows) < 2:
        return None
    t0 = cashflows[0][0]
    years = [((d - t0).days / 365.0) for d, _ in cashflows]
    amounts = [a for _, a in cashflows]

    if not (any(a < 0 for a in amounts) and any(a > 0 for a in amounts)):
        return None

    def npv(rate: float) -> float:
        if rate <= -0.999999:
            return float("inf")
        return sum(a / ((1.0 + rate) ** y) for a, y in zip(amounts, years))

    rate = guess
    for _ in range(80):
        f = npv(rate)
        if not math.isfinite(f):
            break
        step = 1e-6
        d = (npv(rate + step) - f) / step
        if abs(d) < 1e-12:
            break
        new = rate - f / d
        if not math.isfinite(new) or new <= -0.999:
            break
        if abs(new - rate) < 1e-8:
            return round(new, 6)
        rate = new

    lo, hi = -0.95, 10.0
    f_lo = npv(lo)
    if not math.isfinite(f_lo):
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if not math.isfinite(f_mid):
            return None
        if abs(f_mid) < 1e-9:
            return round(mid, 6)
        if (f_lo < 0) != (f_mid < 0):
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return round((lo + hi) / 2, 6)


# ───────────────────────────────────────────────────────────── SIP

def simulate_sip(ticker: str, monthly: float, start: str, end: str) -> dict:
    """Invest ``monthly`` on the first trading day of each month and report.

    Also runs the same total capital as a single lump sum at the start, because
    the honest comparison for "is SIP good?" is against the alternative, not
    against zero.
    """
    prices = load_prices(ticker, start, end)

    # First available trading day of each calendar month.
    picks: list[tuple[date, float]] = []
    seen_months: set[tuple[int, int]] = set()
    for ts, price in prices.items():
        d = ts.date()
        key = (d.year, d.month)
        if key not in seen_months and price > 0:
            seen_months.add(key)
            picks.append((d, float(price)))

    if len(picks) < 2:
        raise ValueError("Not enough history for a SIP simulation (need 2+ months)")

    units = 0.0
    invested = 0.0
    cashflows: list[tuple[date, float]] = []
    curve: list[dict] = []
    for d, price in picks:
        units += monthly / price
        invested += monthly
        cashflows.append((d, -monthly))
        curve.append({
            "date": d.isoformat(),
            "invested": round(invested, 2),
            "value": round(units * price, 2),
        })

    last_date = prices.index[-1].date()
    last_price = float(prices.iloc[-1])
    final_value = units * last_price
    cashflows.append((last_date, final_value))

    years = max((last_date - picks[0][0]).days / 365.0, 1e-9)

    # Lump sum: the same total money, invested once at the start.
    lump_units = invested / picks[0][1]
    lump_value = lump_units * last_price

    sip_xirr = xirr(cashflows)
    return {
        "ticker": ticker.upper(),
        "monthly": monthly,
        "start": picks[0][0].isoformat(),
        "end": last_date.isoformat(),
        "months": len(picks),
        "invested": round(invested, 2),
        "final_value": round(final_value, 2),
        "gain": round(final_value - invested, 2),
        "gain_pct": round((final_value / invested - 1.0) * 100, 2) if invested else 0.0,
        "xirr_pct": round(sip_xirr * 100, 2) if sip_xirr is not None else None,
        "years": round(years, 2),
        "lumpsum_value": round(lump_value, 2),
        "lumpsum_gain_pct": round((lump_value / invested - 1.0) * 100, 2) if invested else 0.0,
        "sip_beat_lumpsum": final_value > lump_value,
        "curve": curve,
        "worst_drawdown_pct": round(
            _max_drawdown([c["value"] for c in curve]) * 100, 2
        ),
    }


# ──────────────────────────────────────────────────────── strategies

def _signals_buy_hold(closes: list[float]) -> list[int]:
    return [1] * len(closes)


def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= window:
            run -= values[i - window]
        if i >= window - 1:
            out[i] = run / window
    return out


def _signals_sma_cross(closes: list[float], fast: int = 50, slow: int = 200) -> list[int]:
    """Hold while the fast average is above the slow one — classic trend rule."""
    f, s = _sma(closes, fast), _sma(closes, slow)
    return [
        1 if (f[i] is not None and s[i] is not None and f[i] > s[i]) else 0
        for i in range(len(closes))
    ]


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    gains = losses = 0.0
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain, loss = max(change, 0.0), max(-change, 0.0)
        if i <= period:
            gains += gain
            losses += loss
            if i == period:
                ag, al = gains / period, losses / period
                out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
                gains, losses = ag, al
        else:
            gains = (gains * (period - 1) + gain) / period
            losses = (losses * (period - 1) + loss) / period
            out[i] = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    return out


def _signals_rsi_meanrev(closes: list[float], low: int = 30, high: int = 70) -> list[int]:
    """Buy when oversold, exit when overbought; hold the position in between."""
    rsi = _rsi(closes)
    out, holding = [], 0
    for v in rsi:
        if v is not None:
            if v < low:
                holding = 1
            elif v > high:
                holding = 0
        out.append(holding)
    return out


STRATEGIES = {
    "buy_hold": ("Buy and hold", _signals_buy_hold),
    "sma_cross": ("50/200 moving-average trend", _signals_sma_cross),
    "rsi_meanrev": ("RSI 30/70 mean reversion", _signals_rsi_meanrev),
}


def backtest(ticker: str, start: str, end: str,
             cost: float = DEFAULT_COST) -> dict:
    """Run every strategy over real prices and compare them to buy-and-hold.

    Trades are charged ``cost`` each way. Positions are taken on the *next* bar
    after a signal, never the same bar, so the result does not quietly assume
    you could act on a close you had not seen yet.
    """
    prices = load_prices(ticker, start, end)
    dates = [ts.date().isoformat() for ts in prices.index]
    closes = [float(v) for v in prices.values]
    if len(closes) < 30:
        raise ValueError("Need at least 30 trading days to backtest")

    years = max((prices.index[-1].date() - prices.index[0].date()).days / 365.0, 1e-9)

    results = []
    for key, (label, fn) in STRATEGIES.items():
        signals = fn(closes)
        equity, position, trades = [1.0], 0, 0
        for i in range(1, len(closes)):
            wanted = signals[i - 1]          # act on yesterday's signal
            if wanted != position:
                trades += 1
                equity[-1] *= (1.0 - cost)   # pay to switch
                position = wanted
            ret = closes[i] / closes[i - 1] - 1.0
            equity.append(equity[-1] * (1.0 + (ret if position else 0.0)))

        stats = _stats(equity, years)
        results.append({
            "key": key, "label": label, "trades": trades,
            "curve": [round(v, 5) for v in equity], **stats,
        })

    hold = next(r for r in results if r["key"] == "buy_hold")
    for r in results:
        r["vs_buy_hold"] = round(r["total_return"] - hold["total_return"], 4)
        r["beats_buy_hold"] = r["total_return"] > hold["total_return"]

    # The benchmark index, so "did this beat the market?" is answerable too.
    bench_symbol = benchmark_for(ticker)
    bench = None
    try:
        bseries = load_prices(bench_symbol, start, end)
        bvalues = [float(v) for v in bseries.values]
        norm = [v / bvalues[0] for v in bvalues]
        bench = {"symbol": bench_symbol, "label": f"{bench_symbol} (index)",
                 **_stats(norm, years)}
    except Exception as exc:  # noqa: BLE001 - benchmark is a nice-to-have
        logger.warning("benchmark %s failed: %s", bench_symbol, exc)

    return {
        "ticker": ticker.upper(), "start": dates[0], "end": dates[-1],
        "years": round(years, 2), "cost_per_trade_pct": round(cost * 100, 3),
        "dates": dates, "results": results, "benchmark": bench,
        "best": max(results, key=lambda r: r["total_return"])["key"],
    }


# ───────────────────────────────────────────────── SIP comparison

def compare_sip(tickers: list[str], monthly: float, years: int = 10) -> dict:
    """Run the same SIP across several instruments and rank by XIRR.

    Intended for comparing an index fund against individual stocks, which is the
    comparison that actually matters when choosing where to put a monthly SIP.
    """
    end = date.today()
    start = end - timedelta(days=int(years * 365.25))
    rows, errors = [], []
    for t in tickers:
        t = t.strip()
        if not t:
            continue
        try:
            r = simulate_sip(t, monthly, start.isoformat(), end.isoformat())
            rows.append({
                "ticker": r["ticker"], "invested": r["invested"],
                "final_value": r["final_value"], "gain_pct": r["gain_pct"],
                "xirr_pct": r["xirr_pct"], "years": r["years"],
                "worst_drawdown_pct": r["worst_drawdown_pct"],
                "months": r["months"],
            })
        except Exception as exc:  # noqa: BLE001 - report, don't abort the set
            errors.append({"ticker": t, "error": str(exc)[:200]})

    rows.sort(key=lambda r: (r["xirr_pct"] is not None, r["xirr_pct"] or -999), reverse=True)
    return {"monthly": monthly, "years": years, "rows": rows, "errors": errors}
