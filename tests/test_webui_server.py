"""Dashboard server: access control, event streaming, and run bookkeeping."""

import base64
import threading

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from webui import run_manager, server  # noqa: E402
from webui.run_manager import Run, RunManager  # noqa: E402


@pytest.fixture(autouse=True)
def _no_optional_keys(monkeypatch):
    # A developer's .env may carry these; tests must not depend on them.
    for var in ("WEBUI_PASSWORD",):
        monkeypatch.delenv(var, raising=False)


def _basic(password, user="me"):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


# ─────────────────────────────────────────────────────── access control

def test_open_when_no_password_is_set():
    assert TestClient(server.app).get("/api/config").status_code == 200


def test_password_required_when_set(monkeypatch):
    monkeypatch.setenv("WEBUI_PASSWORD", "s3cret")
    client = TestClient(server.app)
    r = client.get("/api/config")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")
    assert client.post("/api/run", json={"ticker": "NVDA"}).status_code == 401
    assert client.get("/api/config", headers=_basic("wrong")).status_code == 401
    assert client.get("/api/config", headers=_basic("s3cret")).status_code == 200


def test_malformed_auth_header_is_rejected(monkeypatch):
    monkeypatch.setenv("WEBUI_PASSWORD", "s3cret")
    client = TestClient(server.app)
    for header in ("Basic !!!notbase64", "Bearer s3cret", "Basic"):
        assert client.get("/api/config", headers={"Authorization": header}).status_code == 401


def test_config_never_returns_key_values(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "fred-secret-value")
    body = TestClient(server.app).get("/api/config").text
    assert "fred-secret-value" not in body
    assert '"fred":true' in body.replace(" ", "")


def test_public_bind_without_password_refuses_to_start(monkeypatch):
    import webui.__main__ as entry

    monkeypatch.setattr(entry, "HOST", "0.0.0.0")
    monkeypatch.delenv("WEBUI_ALLOW_PUBLIC", raising=False)
    started = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: started.append(1))
    with pytest.raises(SystemExit):
        entry.main()
    assert not started

    monkeypatch.setenv("WEBUI_PASSWORD", "x")
    monkeypatch.setenv("WEBUI_OPEN", "0")
    entry.main()
    assert started


# ─────────────────────────────────────────────────────── streaming

def _finished_run(n_events=3):
    run = Run("NVDA", "2024-05-10", ["market"])
    for i in range(n_events):
        run.emit("tool", tool=f"t{i}")
    run.status = "done"
    run.emit("eof")
    return run


def test_follow_delivers_every_event_once_per_subscriber():
    run = _finished_run()
    first = [e["kind"] for e in run.follow(timeout=0.01) if e]
    second = [e["kind"] for e in run.follow(timeout=0.01) if e]
    assert first == second == ["tool", "tool", "tool", "eof"]


def test_follow_waits_for_live_events():
    run = Run("NVDA", "2024-05-10", ["market"])
    got = []

    def consume():
        got.extend(e["tool"] for e in run.follow(timeout=0.05) if e and e["kind"] == "tool")

    t = threading.Thread(target=consume)
    t.start()
    run.emit("tool", tool="a")
    run.emit("tool", tool="b")
    run.emit("eof")
    t.join(timeout=5)
    assert got == ["a", "b"]


def test_stream_endpoint_sends_ids_and_resumes(monkeypatch):
    mgr = RunManager()
    run = _finished_run()
    mgr.runs[run.id] = run
    monkeypatch.setattr(server, "MANAGER", mgr)
    client = TestClient(server.app)

    full = client.get(f"/api/run/{run.id}/stream").text
    assert full.count("data: ") == 4
    assert "id: 0\n" in full and "id: 3\n" in full

    resumed = client.get(f"/api/run/{run.id}/stream", headers={"Last-Event-ID": "1"}).text
    assert resumed.count("data: ") == 2        # events 2 and 3 only
    assert "id: 2\n" in resumed


def test_finished_runs_are_pruned(monkeypatch):
    monkeypatch.setattr(run_manager, "MAX_KEPT_RUNS", 2)
    mgr = RunManager()
    for _ in range(4):
        r = _finished_run(0)
        mgr.runs[r.id] = r
    monkeypatch.setattr(mgr, "_execute", lambda run: None)
    newest = mgr.start("AAPL", "2024-05-10", ["market"])
    assert newest.id in mgr.runs
    assert len(mgr.runs) == 3                  # 2 kept finished + the new one


def test_market_range_is_labelled_as_period(monkeypatch):
    import pandas as pd

    idx = pd.bdate_range("2024-01-01", periods=30)
    frame = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0,
                          "Close": [float(i) for i in range(1, 31)], "Volume": 1}, index=idx)
    frame.index.name = "Date"

    class FakeTicker:
        def __init__(self, sym):
            pass

        def history(self, **kwargs):
            return frame

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    body = TestClient(server.app).get("/api/market/NVDA?period=1mo").json()
    assert body["high"] == 30 and body["low"] == 1
    assert "high_52w" not in body
