"""Turn raw provider exceptions into something a person can act on.

A Gemini free-tier refusal arrives as ~1.5 KB of nested JSON. Dumping that into
the UI tells the user nothing useful, so this maps the common failure modes onto
a short title, an explanation, and concrete next steps.
"""

from __future__ import annotations

import re

# "quotaValue': '20'" — the daily/minute allowance the provider enforced.
_QUOTA_VALUE_RE = re.compile(r"quotaValue['\"]?:\s*['\"](\d+)['\"]")
# "model: gemini-3.5-flash" or "model 'gemini-3.5-flash'"
_MODEL_RE = re.compile(r"model[:\s]+['\"]?([\w.\-]+)['\"]?")
_RETRY_RE = re.compile(r"[Rr]etry in ([\d.]+)s")


def classify(exc: BaseException) -> dict:
    """Return {kind, title, message, hints[]} for an exception from a run."""
    text = f"{type(exc).__name__}: {exc}"
    low = text.lower()

    if "resource_exhausted" in low or "429" in text or "quota" in low or "rate limit" in low:
        return _quota(text)

    if any(k in low for k in ("api key not valid", "api_key_invalid", "unauthenticated",
                              "invalid api key", "permission_denied", "401", "403")):
        return {
            "kind": "auth",
            "title": "API key rejected",
            "message": "The LLM provider refused the configured API key.",
            "hints": [
                "Check GOOGLE_API_KEY in .env has no stray spaces or quotes.",
                "Confirm the key is still active at https://aistudio.google.com/apikey",
            ],
        }

    if "nomarketdataerror" in low or "no market data" in low or "no ohlcv data" in low:
        m = re.search(r"(?:No market data for|No OHLCV data available for)\s*'?([\w.^=-]+)", text)
        symbol = m.group(1).rstrip(".") if m else ""
        return {
            "kind": "no_data",
            "title": f"No price data for {symbol or 'that ticker'}",
            "message": (
                "Yahoo Finance returned no rows for this symbol at the requested "
                "analysis date."
            ),
            "hints": [
                "The ticker may have listed after that date (recent IPO or demerger) — try a later date.",
                "Indian listings need a suffix: .NS for NSE, .BO for BSE.",
                "Type the company name in the instrument box and pick from the suggestions.",
            ],
        }

    if any(k in low for k in ("connectionerror", "timeout", "temporarily unavailable",
                              "503", "502", "getaddrinfo")):
        return {
            "kind": "network",
            "title": "Network problem",
            "message": "A data or model request could not reach its server.",
            "hints": ["Check your connection or proxy, then run again."],
        }

    return {
        "kind": "unknown",
        "title": type(exc).__name__,
        "message": str(exc)[:600],
        "hints": [],
    }


def _quota(text: str) -> dict:
    quota = _QUOTA_VALUE_RE.search(text)
    model = _MODEL_RE.search(text)
    retry = _RETRY_RE.search(text)

    model_name = model.group(1) if model else "the configured model"
    limit = quota.group(1) if quota else None

    if limit and int(limit) <= 100:
        # Small numbers are the free tier's per-DAY cap, not a per-minute burst.
        message = (
            f"The free tier allows {limit} requests per day for {model_name}, "
            f"and that allowance is used up. One analysis makes many calls, so "
            f"this model supports roughly one run per day."
        )
        hints = [
            "Switch the deep model to gemini-3.1-flash-lite in .env — it has a much larger free allowance.",
            "Run fewer analysts, or set TRADINGAGENTS_MAX_DEBATE_ROUNDS=1, to spend fewer calls per run.",
            "Wait for the daily reset (midnight Pacific), or use a paid key.",
        ]
    else:
        message = (
            f"{model_name} is rate limited right now"
            + (f" (limit {limit})." if limit else ".")
        )
        hints = ["Wait a moment and run again — this is a short-term throttle."]
        if retry:
            hints.insert(0, f"The provider suggested retrying in ~{retry.group(1)}s.")

    return {
        "kind": "quota",
        "title": "LLM quota exhausted",
        "message": message,
        "hints": hints,
        "docs": "https://ai.google.dev/gemini-api/docs/rate-limits",
    }
