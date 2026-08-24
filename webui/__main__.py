"""Entry point: ``python -m webui``.

Binds to 127.0.0.1 by default so the dashboard is not exposed to the network.
Set WEBUI_HOST=0.0.0.0 when running inside a container or Codespace, where the
port is forwarded rather than reachable directly.
"""

from __future__ import annotations

import os
import webbrowser

import uvicorn

HOST = os.getenv("WEBUI_HOST", "127.0.0.1")
PORT = int(os.getenv("WEBUI_PORT", "8000"))


def main() -> None:
    url = f"http://{'localhost' if HOST in ('127.0.0.1', '0.0.0.0') else HOST}:{PORT}"
    print(f"\n  TradingAgents dashboard -> {url}\n")
    if os.getenv("WEBUI_OPEN", "1") == "1" and HOST == "127.0.0.1":
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - headless environments have no browser
            pass
    uvicorn.run("webui.server:app", host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
