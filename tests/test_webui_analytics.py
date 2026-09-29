"""The dashboard's evidence tools: XIRR, drawdown, SIP and backtest maths.

These numbers are what the dashboard shows people deciding where to put their
savings, so they are pinned against hand-computed values on synthetic prices.
"""

from datetime import date

import pandas as pd
import pytest

from webui import analytics


def _series(closes, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.Series(closes, index=idx, dtype=float)


@pytest.fixture
def prices(monkeypatch):
    """Route load_prices to an in-memory series instead of Yahoo."""
    table = {}

    def fake(ticker, start, end):
        if ticker not in table:
            raise ValueError(f"no data for {ticker}")
        return table[ticker]

    monkeypatch.setattr(analytics, "load_prices", fake)
    return table


# ─────────────────────────────────────────────────────────── XIRR

def test_xirr_one_year_ten_percent():
    flows = [(date(2020, 1, 1), -100.0), (date(2021, 1, 1), 110.0)]
    # 366 days in 2020; XIRR uses a 365-day year, so the rate is a hair under 10%.
    assert analytics.xirr(flows) == pytest.approx(0.0997, abs=1e-3)


def test_xirr_needs_both_signs():
    assert analytics.xirr([(date(2020, 1, 1), -100.0), (date(2021, 1, 1), -5.0)]) is None
    assert analytics.xirr([(date(2020, 1, 1), -100.0)]) is None


def test_xirr_total_loss_is_near_minus_one():
    flows = [(date(2020, 1, 1), -100.0), (date(2021, 1, 1), 1.0)]
    assert analytics.xirr(flows) == pytest.approx(-0.99, abs=0.01)


def test_max_drawdown():
    assert analytics._max_drawdown([100, 120, 60, 90, 130]) == pytest.approx(-0.5)
    assert analytics._max_drawdown([1, 2, 3]) == 0.0


# ─────────────────────────────────────────────────────────── SIP

def test_sip_flat_price_returns_zero(prices):
    prices["FLAT"] = _series([100.0] * 300)
    r = analytics.simulate_sip("FLAT", 1000, "2020-01-01", "2021-03-01")
    assert r["gain"] == pytest.approx(0.0)
    assert r["xirr_pct"] == pytest.approx(0.0, abs=0.01)
    assert r["months"] == len({(d.year, d.month) for d in prices["FLAT"].index})


def test_sip_buys_first_trading_day_of_each_month(prices):
    prices["UP"] = _series([float(100 + i) for i in range(70)])
    r = analytics.simulate_sip("UP", 1000, "2020-01-01", "2020-04-30")
    assert [c["date"][:7] for c in r["curve"]] == ["2020-01", "2020-02", "2020-03", "2020-04"]
    assert r["invested"] == 4000


# ─────────────────────────────────────────────────────────── backtest

def test_backtest_does_not_trade_on_the_signal_close(prices, monkeypatch):
    """A signal from close t may only earn returns from close t+1 onward.

    The strategy below goes long on bar 50 (its signal sees closes[50]).
    Bar 51 jumps +50%. Trading at the signal close would capture that jump;
    trading one close later must not.
    """
    closes = [100.0] * 51 + [150.0] + [150.0] * 20
    prices["JUMP"] = _series(closes)
    prices["SPY"] = _series([100.0] * len(closes))

    def enter_at_bar_50(cs):
        return [1 if i >= 50 else 0 for i in range(len(cs))]

    monkeypatch.setattr(analytics, "STRATEGIES", {
        "buy_hold": ("Buy and hold", analytics._signals_buy_hold),
        "late": ("late entry", enter_at_bar_50),
    })
    r = analytics.backtest("JUMP", "2020-01-01", "2021-01-01", cost=0.0)
    late = next(x for x in r["results"] if x["key"] == "late")
    hold = next(x for x in r["results"] if x["key"] == "buy_hold")
    assert hold["total_return"] == pytest.approx(0.5)
    assert late["total_return"] == pytest.approx(0.0)


def test_backtest_charges_costs(prices, monkeypatch):
    prices["FLAT"] = _series([100.0] * 60)
    prices["SPY"] = _series([100.0] * 60)

    def flip_every_bar(cs):
        return [i % 2 for i in range(len(cs))]

    monkeypatch.setattr(analytics, "STRATEGIES", {
        "buy_hold": ("Buy and hold", analytics._signals_buy_hold),
        "flip": ("flip", flip_every_bar),
    })
    r = analytics.backtest("FLAT", "2020-01-01", "2021-01-01", cost=0.01)
    flip = next(x for x in r["results"] if x["key"] == "flip")
    assert flip["trades"] > 50
    assert flip["total_return"] < -0.4       # costs alone destroy a flat market
    assert flip["beats_buy_hold"] is False


def test_backtest_rejects_short_history(prices):
    prices["TINY"] = _series([100.0] * 10)
    with pytest.raises(ValueError):
        analytics.backtest("TINY", "2020-01-01", "2021-01-01")


def test_benchmark_by_suffix():
    assert analytics.benchmark_for("RELIANCE.NS") == "^NSEI"
    assert analytics.benchmark_for("AAPL") == "SPY"


def test_index_is_its_own_benchmark():
    # Not SPY: NIFTY against the S&P 500 compares different markets and currencies.
    assert analytics.benchmark_for("^NSEI") == "^NSEI"
    assert analytics.benchmark_for("^bsesn") == "^BSESN"
