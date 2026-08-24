"""Read past runs from the on-disk artifacts TradingAgents already writes.

Three sources, all under ``~/.tradingagents`` (override via TRADINGAGENTS_*):

* ``memory/trading_memory.md`` — the decision log: one entry per completed run,
  with the realised-return reflection appended on the next same-ticker run.
* ``logs/<TICKER>/<date>/reports/*.md`` — per-agent report trees (CLI runs).
* ``logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<date>.json`` —
  full final state (``main.py`` / programmatic runs).

Everything here is read-only and defensive: a missing or half-written file
yields an empty list rather than an exception, because the dashboard polls
these while a run may be writing them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tradingagents.default_config import DEFAULT_CONFIG

# Entries are delimited by an HTML comment the writer appends after each run.
_ENTRY_END = "<!-- ENTRY_END -->"
# Header looks like: [2024-05-10 | NVDA | Buy | pending]
_HEADER_RE = re.compile(r"^\[([\d-]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^\]]*)\]")
_FIELD_RE = re.compile(r"^\*\*(.+?)\*\*:\s*(.*)$", re.MULTILINE)

# Final-state keys that differ from the report-tree filenames.
_STATE_ALIASES = {"trader_investment_plan": "trader_investment_decision"}

# ``write_report_tree`` names files by role inside numbered stage directories
# (1_analysts/market.md, 5_portfolio/decision.md, ...). Map those stems onto the
# section keys the rest of the app uses. The older flat layout already uses the
# section names, so unmapped stems pass through untouched.
_FILE_KEYS = {
    "market": "market_report",
    "sentiment": "sentiment_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
    "bull": "bull_report",
    "bear": "bear_report",
    "manager": "investment_plan",
    "trader": "trader_investment_plan",
    "aggressive": "risk_aggressive",
    "conservative": "risk_conservative",
    "neutral": "risk_neutral",
    "decision": "final_trade_decision",
}

REPORT_ORDER = [
    ("market_report", "Market"),
    ("sentiment_report", "Sentiment"),
    ("news_report", "News"),
    ("fundamentals_report", "Fundamentals"),
    ("bull_report", "Bull"),
    ("bear_report", "Bear"),
    ("investment_plan", "Research"),
    ("trader_investment_plan", "Trader"),
    ("risk_aggressive", "Risk: Aggressive"),
    ("risk_conservative", "Risk: Conservative"),
    ("risk_neutral", "Risk: Neutral"),
    ("final_trade_decision", "Decision"),
]


def _home() -> Path:
    # results_dir points at <home>/logs; its parent is the TradingAgents home.
    return Path(DEFAULT_CONFIG["results_dir"]).parent


def memory_log_path() -> Path:
    import os

    override = os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH")
    if override:
        return Path(override)
    return _home() / "memory" / "trading_memory.md"


def logs_dir() -> Path:
    return Path(DEFAULT_CONFIG["results_dir"])


def parse_decision_log() -> list[dict]:
    """Return decision-log entries, newest first.

    Each entry: date, ticker, rating, outcome, decision fields (price target,
    time horizon, thesis, summary) and the reflection text when one exists.
    """
    path = memory_log_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    entries: list[dict] = []
    for block in raw.split(_ENTRY_END):
        block = block.strip()
        if not block:
            continue
        header = _HEADER_RE.search(block)
        if not header:
            continue
        date, ticker, rating, outcome = (g.strip() for g in header.groups())

        fields = {k.strip().lower(): v.strip() for k, v in _FIELD_RE.findall(block)}

        reflection = ""
        if "REFLECTION:" in block:
            reflection = block.split("REFLECTION:", 1)[1].strip()

        decision_body = block
        if "DECISION:" in decision_body:
            decision_body = decision_body.split("DECISION:", 1)[1]
        if "REFLECTION:" in decision_body:
            decision_body = decision_body.split("REFLECTION:", 1)[0]

        entries.append({
            "date": date,
            "ticker": ticker,
            "rating": rating,
            "outcome": outcome or "pending",
            "price_target": fields.get("price target", ""),
            "time_horizon": fields.get("time horizon", ""),
            "executive_summary": fields.get("executive summary", ""),
            "investment_thesis": fields.get("investment thesis", ""),
            "reasoning": fields.get("reasoning", ""),
            "reflection": reflection.strip(),
            "decision_markdown": decision_body.strip(),
        })

    entries.reverse()  # newest first
    return entries


def _alpha_from_outcome(text: str) -> str:
    """Pull a signed percentage out of a reflection sentence, if present."""
    m = re.search(r"([+-]?\d+(?:\.\d+)?)%\s*alpha", text, re.IGNORECASE)
    return f"{m.group(1)}%" if m else ""


def list_runs() -> list[dict]:
    """Merge the decision log with any saved report trees into one run list."""
    runs = parse_decision_log()
    for r in runs:
        r["alpha"] = _alpha_from_outcome(r.get("reflection", ""))
        r["reports_available"] = bool(find_reports(r["ticker"], r["date"]))
    return runs


def find_reports(ticker: str, date: str) -> dict[str, str]:
    """Return {section_key: markdown} for a saved report tree, if one exists.

    Looks in the flat ``reports/`` layout the CLI writes and the numbered
    ``1_analysts/`` … tree that ``write_report_tree`` produces.
    """
    base = logs_dir() / ticker / date
    found: dict[str, str] = {}
    if not base.exists():
        return found

    for md in base.rglob("*.md"):
        key = _FILE_KEYS.get(md.stem, md.stem)
        if key == "complete_report" or key in found:
            continue
        try:
            found[key] = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return found


def find_state_json(ticker: str, date: str) -> dict:
    """Load the full-state JSON a programmatic run writes, if present."""
    p = logs_dir() / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    # File maps date -> state; unwrap when it does.
    if isinstance(data, dict) and date in data and isinstance(data[date], dict):
        return data[date]
    return data if isinstance(data, dict) else {}


def reports_for(ticker: str, date: str) -> list[dict]:
    """Ordered report sections for one run, from either storage layout."""
    md = find_reports(ticker, date)
    state = find_state_json(ticker, date) if not md else {}

    sections = []
    for key, label in REPORT_ORDER:
        content = md.get(key)
        if not content and isinstance(state, dict):
            # The saved state names the trader section differently from the
            # file tree; accept either spelling.
            content = state.get(key) or state.get(_STATE_ALIASES.get(key, ""))
        if isinstance(content, str) and content.strip():
            sections.append({"key": key, "label": label, "markdown": content})
    return sections
