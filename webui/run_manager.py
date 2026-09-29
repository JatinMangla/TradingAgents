"""Launch TradingAgents analyses in a worker thread and stream their progress.

The graph is synchronous and blocking, so each run gets a daemon thread. The
thread pushes events onto a queue that the SSE endpoint drains; the browser
therefore sees agent-by-agent progress as it happens rather than one payload at
the end.

Mirrors the streaming approach in ``cli/main.py``: build the initial state
directly, resolve the instrument identity first (so every agent anchors to the
real company), then iterate ``graph.graph.stream(...)``.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import traceback
import uuid
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from webui.errors import classify

logger = logging.getLogger(__name__)

# Which agent finalises each report section, so the UI can flip a node to
# "done" the moment its section lands in the streamed state.
SECTION_AGENT = {
    "market_report": "Market Analyst",
    "sentiment_report": "Sentiment Analyst",
    "news_report": "News Analyst",
    "fundamentals_report": "Fundamentals Analyst",
    "investment_plan": "Research Manager",
    "trader_investment_plan": "Trader",
    "final_trade_decision": "Portfolio Manager",
}

PIPELINE = [
    "Market Analyst",
    "Sentiment Analyst",
    "News Analyst",
    "Fundamentals Analyst",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Risk Team",
    "Portfolio Manager",
]

_ANALYST_AGENT = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

_ANALYST_NAMES = set(_ANALYST_AGENT.values())

# Finished runs kept in memory for the results view. Each holds every report
# section and event, so an unbounded dict would grow for the server's lifetime.
MAX_KEPT_RUNS = 20


class Run:
    """One analysis: its event queue, replay buffer, and terminal status."""

    def __init__(self, ticker: str, date: str, analysts: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.ticker = ticker.strip().upper()
        self.date = date
        self.analysts = analysts
        self.status = "starting"       # starting | running | done | error
        self.started = datetime.now().isoformat(timespec="seconds")
        self.error: str | None = None
        self.decision: str = ""
        self.sections: dict[str, str] = {}
        # The event log is the single source of truth. Every subscriber reads it
        # through its own cursor, so a reconnecting or second browser tab sees the
        # full stream exactly once. (A shared queue would hand each event to only
        # one reader, and replaying the log *and* draining the queue would
        # deliver every early event twice.)
        self.events: list[dict] = []
        self._cond = threading.Condition()

    def emit(self, kind: str, **payload: Any) -> None:
        evt = {"kind": kind, "ts": datetime.now().strftime("%H:%M:%S"), **payload}
        with self._cond:
            self.events.append(evt)
            self._cond.notify_all()

    def replay(self) -> list[dict]:
        with self._cond:
            return list(self.events)

    def follow(self, start: int = 0, timeout: float = 15.0) -> Iterator[dict | None]:
        """Yield events from index ``start``, then new ones as they arrive.

        Yields ``None`` after ``timeout`` seconds of silence so the caller can
        send a keepalive. Stops after the ``eof`` event.
        """
        cursor = max(0, start)
        while True:
            with self._cond:
                if cursor >= len(self.events):
                    self._cond.wait(timeout)
                batch = self.events[cursor:]
            if not batch:
                yield None
                continue
            for evt in batch:
                cursor += 1
                yield evt
                if evt.get("kind") == "eof":
                    return

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "date": self.date,
            "status": self.status,
            "started": self.started,
            "error": self.error,
            "decision": self.decision,
            "sections": self.sections,
            "analysts": self.analysts,
        }


class RunManager:
    """Owns every run this server has started. In-memory and single-process."""

    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def active(self) -> Run | None:
        for r in self.runs.values():
            if r.status in ("starting", "running"):
                return r
        return None

    def start(self, ticker: str, date: str, analysts: list[str]) -> Run:
        with self._lock:
            existing = self.active()
            if existing:
                # One run at a time: concurrent runs would race on the shared
                # decision log and burn through free-tier LLM rate limits.
                raise RuntimeError(
                    f"A run is already in progress ({existing.ticker} {existing.date})."
                )
            run = Run(ticker, date, analysts)
            self.runs[run.id] = run
            finished = [k for k, r in self.runs.items() if r.status in ("done", "error")]
            for key in finished[: max(0, len(finished) - MAX_KEPT_RUNS)]:
                del self.runs[key]

        threading.Thread(target=self._execute, args=(run,), daemon=True).start()
        return run

    # ---------------------------------------------------------------- worker

    def _execute(self, run: Run) -> None:
        try:
            run.emit("status", status="starting", message="Building agent graph...")
            self._stream_graph(run)
            run.status = "done"
            run.emit("status", status="done", message="Analysis complete.")
        except Exception as exc:                     # noqa: BLE001 - surfaced to UI
            logger.exception("run %s failed", run.id)
            run.status = "error"
            # Raw provider errors are unreadable (a Gemini quota refusal is ~1.5KB
            # of nested JSON), so hand the UI a classified, actionable version.
            info = classify(exc)
            run.error = f"{info['title']}: {info['message']}"
            run.emit(
                "status",
                status="error",
                message=info["message"],
                error_kind=info["kind"],
                title=info["title"],
                hints=info.get("hints", []),
                docs=info.get("docs", ""),
                detail=traceback.format_exc()[-2000:],
            )
        finally:
            run.emit("eof")

    def _stream_graph(self, run: Run) -> None:
        from cli.utils import detect_asset_type
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # Deep copy: the config holds nested dicts (data_vendors, benchmark_map)
        # that a shallow copy would share with every later run.
        config = copy.deepcopy(DEFAULT_CONFIG)
        selected = run.analysts or ["market", "social", "news", "fundamentals"]

        graph = TradingAgentsGraph(selected_analysts=selected, debug=False, config=config)

        asset_type = detect_asset_type(run.ticker)
        instrument_context = graph.resolve_instrument_context(run.ticker, asset_type)

        # resolve_instrument_context returns a prompt string, not a dict; the
        # resolved company name is embedded in it as "Company: <name>;".
        company = ""
        match = re.search(r"Company:\s*([^;]+);", instrument_context or "")
        if match:
            company = match.group(1).strip()

        chosen = {_ANALYST_AGENT[k] for k in selected if k in _ANALYST_AGENT}
        pipeline = [a for a in PIPELINE if a not in _ANALYST_NAMES or a in chosen]

        run.emit(
            "meta",
            company=company,
            asset_type=getattr(asset_type, "value", str(asset_type)),
            provider=config.get("llm_provider"),
            deep=config.get("deep_think_llm"),
            quick=config.get("quick_think_llm"),
            pipeline=pipeline,
        )

        # propagate() normally resolves outstanding entries (fetching each past
        # decision's realised return and writing a reflection) before running.
        # We stream the graph directly, so do it here or the learning loop never
        # advances for dashboard runs.
        try:
            graph._resolve_pending_entries(run.ticker)
        except Exception as exc:                      # noqa: BLE001 - non-fatal
            logger.warning("could not resolve pending entries: %s", exc)

        past_context = ""
        try:
            past_context = graph.memory_log.get_past_context(run.ticker) or ""
        except Exception as exc:                      # noqa: BLE001 - non-fatal
            logger.warning("could not load past context: %s", exc)

        state = graph.propagator.create_initial_state(
            run.ticker, run.date, asset_type=asset_type,
            past_context=past_context,
            instrument_context=instrument_context,
        )
        args = graph.propagator.get_graph_args()

        run.status = "running"
        first = _ANALYST_AGENT.get(selected[0], "Market Analyst")
        run.emit("agent", agent=first, state="running")
        run.emit("status", status="running", message=f"Analyzing {run.ticker} on {run.date}...")

        final_state: dict = {}
        seen_msg_ids: set[str] = set()
        announced: set[str] = set()   # agents already reported done

        for chunk in graph.graph.stream(state, **args):
            if not isinstance(chunk, dict):
                continue
            final_state.update(chunk)

            for message in chunk.get("messages", []) or []:
                mid = getattr(message, "id", None)
                if mid is not None:
                    if mid in seen_msg_ids:
                        continue
                    seen_msg_ids.add(mid)
                for call in getattr(message, "tool_calls", None) or []:
                    name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
                    if name:
                        run.emit("tool", tool=name)

            # A section appearing in the stream means its agent just finished.
            for key, agent in SECTION_AGENT.items():
                content = chunk.get(key)
                if isinstance(content, str) and content.strip() and key not in run.sections:
                    run.sections[key] = content
                    run.emit("agent", agent=agent, state="done")
                    run.emit("section", key=key, agent=agent, markdown=content)

            self._emit_debate_progress(run, chunk, announced)

        decision = final_state.get("final_trade_decision") or run.sections.get(
            "final_trade_decision", ""
        )
        run.decision = decision if isinstance(decision, str) else ""

        # Persist under the CLI's layout (<results_dir>/<TICKER>/<date>/reports)
        # rather than save_reports' default (<results_dir>/reports/<TICKER>_<ts>),
        # so the history reader finds these alongside CLI-produced runs.
        try:
            save_path = (
                Path(config["results_dir"]) / run.ticker / run.date / "reports"
            )
            path = graph.save_reports(final_state, run.ticker, save_path=save_path)
            run.emit("saved", path=str(path))
        except Exception as exc:                      # noqa: BLE001 - non-fatal
            logger.warning("could not save reports for %s: %s", run.ticker, exc)
            run.emit("warn", message=f"Reports not saved: {exc}")

        # Record the decision so it shows in history and so the next run for this
        # ticker can score it against the benchmark and reflect on it.
        if run.decision:
            try:
                graph.memory_log.store_decision(
                    ticker=run.ticker,
                    trade_date=run.date,
                    final_trade_decision=run.decision,
                )
                run.emit("logged", message="Decision written to the decision log.")
            except Exception as exc:                  # noqa: BLE001 - non-fatal
                logger.warning("could not store decision: %s", exc)
                run.emit("warn", message=f"Decision not logged: {exc}")

        run.emit("decision", markdown=run.decision)

    @staticmethod
    def _emit_debate_progress(run: Run, chunk: dict, announced: set[str]) -> None:
        """Surface bull/bear and risk-team turns the first time each appears.

        The debate histories stay populated in every later chunk, so without the
        ``announced`` guard each agent would re-emit "done" on every step.
        """
        debate = chunk.get("investment_debate_state")
        if isinstance(debate, dict):
            for who, agent in (("bull_history", "Bull Researcher"),
                               ("bear_history", "Bear Researcher")):
                if (debate.get(who) or "").strip() and agent not in announced:
                    announced.add(agent)
                    run.emit("agent", agent=agent, state="done")

        risk = chunk.get("risk_debate_state")
        if isinstance(risk, dict) and "Risk Team" not in announced and any(
            (risk.get(k) or "").strip()
            for k in ("risky_history", "safe_history", "neutral_history")
        ):
            announced.add("Risk Team")
            run.emit("agent", agent="Risk Team", state="done")


MANAGER = RunManager()
