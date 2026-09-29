"""Historical analyses must not see data published after the analysis date."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from tradingagents.dataflows import y_finance
from tradingagents.dataflows.stockstats_utils import filter_financials_by_date
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _statements(*period_ends):
    return pd.DataFrame({pd.Timestamp(d): [1.0] for d in period_ends}, index=["Revenue"])


def test_quarter_not_visible_before_it_was_reported():
    # NVDA's quarter ending 2024-04-28 was reported on 2024-05-22.
    data = _statements("2024-01-28", "2024-04-28")
    visible = filter_financials_by_date(data, "2024-05-10", "quarterly")
    assert list(visible.columns) == [pd.Timestamp("2024-01-28")]


def test_quarter_visible_after_publication_lag():
    data = _statements("2024-01-28", "2024-04-28")
    visible = filter_financials_by_date(data, "2024-06-30", "quarterly")
    assert len(visible.columns) == 2


def test_annual_statements_use_longer_lag():
    data = _statements("2023-12-31")
    assert filter_financials_by_date(data, "2024-02-15", "annual").empty
    assert not filter_financials_by_date(data, "2024-04-15", "annual").empty


def test_no_date_keeps_everything():
    data = _statements("2024-01-28")
    assert filter_financials_by_date(data, None).equals(data)


_INFO = {"longName": "NVIDIA", "sector": "Tech", "marketCap": 4e12,
         "trailingPE": 50.0, "fiftyTwoWeekHigh": 200.0, "totalRevenue": 1e11}


def _fundamentals(curr_date):
    ticker = MagicMock()
    ticker.info = _INFO
    with patch.object(y_finance.yf, "Ticker", return_value=ticker):
        return y_finance.get_fundamentals("NVDA", curr_date)


def test_historical_fundamentals_drop_todays_price_fields():
    out = _fundamentals("2024-05-10")
    assert "Market Cap" not in out and "PE Ratio" not in out and "52 Week High" not in out
    assert "Revenue (TTM)" in out
    assert "WARNING" in out and "2024-05-10" in out


def test_current_fundamentals_keep_everything():
    out = _fundamentals(datetime.now().strftime("%Y-%m-%d"))
    assert "Market Cap" in out and "WARNING" not in out


# ─────────────────────────────────────────────── reflection scoring window

def _price_df(n):
    return pd.DataFrame({"Close": [100.0 + i for i in range(n)]})


def test_recent_decision_stays_pending_until_window_passes():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    with patch("yfinance.Ticker") as cls:
        cls.return_value.history.return_value = _price_df(2)
        result = TradingAgentsGraph._fetch_returns(MagicMock(), "NVDA", yesterday, holding_days=5)
    assert result == (None, None, None)


def test_long_horizon_window_is_not_truncated():
    with patch("yfinance.Ticker") as cls:
        cls.return_value.history.return_value = _price_df(40)
        TradingAgentsGraph._fetch_returns(MagicMock(), "NVDA", "2025-01-02", holding_days=21)
        end = cls.return_value.history.call_args.kwargs["end"]
    span = (datetime.strptime(end, "%Y-%m-%d") - datetime(2025, 1, 2)).days
    assert span >= 21 * 7 / 5          # enough calendar days for 21 sessions


def test_holding_days_come_from_config():
    graph = MagicMock()
    graph.config = {"reflection_holding_days": 21}
    assert TradingAgentsGraph._reflection_holding_days(graph) == 21
    graph.config = {"reflection_holding_days": "bogus"}
    assert TradingAgentsGraph._reflection_holding_days(graph) == 5
    graph.config = {}
    assert TradingAgentsGraph._reflection_holding_days(graph) == 5
