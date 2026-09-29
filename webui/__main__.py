"""Entry point: ``python -m webui``.

Binds to 127.0.0.1 by default so the dashboard is not exposed to the network.
Set WEBUI_HOST=0.0.0.0 when running inside a container or Codespace, where the
port is forwarded rather than reachable directly.

A non-loopback bind also requires WEBUI_PASSWORD. Without it, anyone who can
reach the port can start analyses on your LLM key and read your decision
history. Set WEBUI_ALLOW_PUBLIC=1 only when something in front of the app (a
private Codespaces port, an authenticating proxy) already restricts access.
"""

from __future__ import annotations

import contextlib
import os
import sys
import webbrowser

import uvicorn

HOST = os.getenv("WEBUI_HOST", "127.0.0.1")
PORT = int(os.getenv("WEBUI_PORT", "8000"))

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def main() -> None:
    if (HOST not in _LOOPBACK and not os.getenv("WEBUI_PASSWORD")
            and os.getenv("WEBUI_ALLOW_PUBLIC") != "1"):
        sys.exit(
            f"Refusing to serve on {HOST} without WEBUI_PASSWORD: anyone who can reach "
            f"this port could run analyses on your LLM key.\n"
            f"Set WEBUI_PASSWORD (browsers will prompt for it), or set "
            f"WEBUI_ALLOW_PUBLIC=1 if access is already restricted another way."
        )

    url = f"http://{'localhost' if HOST in ('127.0.0.1', '0.0.0.0') else HOST}:{PORT}"
    print(f"\n  TradingAgents dashboard -> {url}\n")
    if os.getenv("WEBUI_OPEN", "1") == "1" and HOST == "127.0.0.1":
        # Headless environments have no browser.
        with contextlib.suppress(Exception):
            webbrowser.open(url)
    uvicorn.run("webui.server:app", host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
