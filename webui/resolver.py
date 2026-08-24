"""Turn whatever a person types into a runnable Yahoo Finance ticker.

The pipeline needs a symbol (``^NSEI``), but people type names ("nifty 50",
"hitachi energy", "power india"). This module bridges that gap:

* an input that is already a working ticker is used as-is;
* anything else is searched, filtered to symbols the pipeline can actually run,
  ranked, and returned as candidates for the user to pick from.

Nothing here guesses silently when the answer is unclear — an ambiguous query
comes back as a candidate list so the person chooses, rather than the system
quietly analysing the wrong instrument.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Instrument kinds worth analysing, scored by how well this tool handles them.
# Mutual funds have no news/fundamentals coverage, so they rank last.
_TYPE_SCORE = {
    "EQUITY": 100,
    "INDEX": 90,
    "ETF": 70,
    "CRYPTOCURRENCY": 65,
    "CURRENCY": 30,
    "FUTURE": 25,
    "MUTUALFUND": 5,
}

# Ranking for the SIP tool, where funds and ETFs are the point and a single
# company share is the less likely answer.
_FUND_TYPE_SCORE = {
    "MUTUALFUND": 100,
    "ETF": 95,
    "INDEX": 80,
    "EQUITY": 55,
    "CRYPTOCURRENCY": 20,
    "CURRENCY": 10,
    "FUTURE": 5,
}

# Yahoo lists mutual funds under opaque codes (0P0001J6FU.BO) and returns no
# name for them in search results — the readable name only comes from get_info().
# These are real, useful instruments for SIP, so they are enriched rather than
# discarded.
_OPAQUE_RE = re.compile(r"^0P[0-9A-Z]{6,}\b")

# get_info() is a slow per-symbol network call, so names are cached for the
# process lifetime. Fund names do not change.
_NAME_CACHE: dict[str, str] = {}


def fund_name(symbol: str) -> str:
    """Readable name for an opaque fund code, or '' when unavailable."""
    if symbol in _NAME_CACHE:
        return _NAME_CACHE[symbol]

    import yfinance as yf

    name = ""
    try:
        info = yf.Ticker(symbol).get_info() or {}
        name = info.get("longName") or info.get("shortName") or ""
    except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
        logger.warning("name lookup failed for %s: %s", symbol, exc)
    _NAME_CACHE[symbol] = name
    return name


# Mirrors tradingagents' safe_ticker_component rule, so this module also works
# where the agent stack is not installed (the serverless deploy ships analytics
# only). Tickers become directory names, so anything path-unsafe is rejected.
_TICKER_RE = re.compile(r"^[A-Za-z0-9.^=-]{1,24}$")


def is_path_safe(symbol: str) -> bool:
    """True when the pipeline's filesystem validation accepts this symbol."""
    try:
        from tradingagents.dataflows.utils import safe_ticker_component
    except ImportError:
        return bool(
            isinstance(symbol, str)
            and _TICKER_RE.fullmatch(symbol)
            and set(symbol) != {"."}
        )

    try:
        safe_ticker_component(symbol)
    except (ValueError, TypeError):
        return False
    return True


def has_market_data(symbol: str) -> bool:
    """Cheap check that Yahoo actually returns rows for ``symbol``.

    Fails **open**: a network blip should not block a legitimate ticker, so an
    exception here counts as "assume usable".
    """
    import yfinance as yf

    try:
        return not yf.Ticker(symbol).history(period="5d").empty
    except Exception as exc:  # noqa: BLE001 - transient upstream issues
        logger.warning("data check failed for %s: %s", symbol, exc)
        return True


def has_data_on(symbol: str, trade_date: str) -> bool:
    """True when ``symbol`` has price history around ``trade_date``.

    Distinct from :func:`has_market_data`, which only asks whether the symbol
    trades *today*. A ticker created by a recent demerger (e.g. TMCV.NS) passes
    that check but has nothing at a 2024 analysis date, and the run would fail
    partway through with "No OHLCV data available".
    """
    from datetime import date, timedelta

    import yfinance as yf

    try:
        target = date.fromisoformat(trade_date)
    except (ValueError, TypeError):
        return True                      # unparseable date: let the run decide

    start = (target - timedelta(days=14)).isoformat()
    end = (target + timedelta(days=5)).isoformat()
    try:
        return not yf.Ticker(symbol).history(start=start, end=end).empty
    except Exception as exc:  # noqa: BLE001 - fail open on transient issues
        logger.warning("date-window check failed for %s @ %s: %s", symbol, trade_date, exc)
        return True


def _score(item: dict, query: str, funds: bool = False) -> int:
    """Rank a search hit: instrument kind first, then how well the name matches."""
    symbol = (item.get("symbol") or "").upper()
    name = (item.get("shortname") or item.get("longname") or "").upper()
    q = query.strip().upper()

    kind = (item.get("quoteType") or "").upper()
    # In fund mode the ranking inverts: a mutual fund is the answer, not noise.
    score = (_FUND_TYPE_SCORE if funds else _TYPE_SCORE).get(kind, 10)

    if symbol == q:
        score += 60
    elif symbol.split(".")[0] == q:
        score += 50          # "POWERINDIA" -> POWERINDIA.NS
    elif symbol.startswith(q):
        score += 20

    if name == q:
        score += 40
    elif name.startswith(q):
        score += 20
    elif q in name:
        score += 10

    # Prefer a real primary listing over a foreign cross-listing of the same name.
    if symbol.endswith((".NS", ".BO")) or "." not in symbol:
        score += 8
    return score


def search(query: str, limit: int = 8, funds: bool = False) -> list[dict]:
    """Search Yahoo for ``query`` and return ranked, usable candidates.

    ``funds=True`` ranks mutual funds first and resolves their opaque codes to
    readable names — the mode the SIP tool uses, where a fund is exactly what
    the person means.
    """
    query = (query or "").strip()
    if len(query) < 2:
        return []

    import yfinance as yf

    try:
        quotes = yf.Search(query, max_results=max(limit * 3, 15)).quotes or []
    except Exception as exc:  # noqa: BLE001 - upstream/network
        logger.warning("search failed for %r: %s", query, exc)
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for item in quotes:
        symbol = (item.get("symbol") or "").strip()
        if not symbol or symbol in seen or not is_path_safe(symbol):
            continue
        kind = (item.get("quoteType") or "").upper()
        # Funds are noise when picking a company to analyse, and the point when
        # choosing a SIP.
        if _OPAQUE_RE.match(symbol.upper()) and not funds:
            continue
        seen.add(symbol)

        name = item.get("shortname") or item.get("longname") or ""
        if name == symbol:
            name = ""
        out.append({
            "symbol": symbol,
            "name": name,
            "type": kind.title(),
            "exchange": item.get("exchDisp") or "",
            "_score": _score(item, query, funds=funds),
        })

    out.sort(key=lambda r: r["_score"], reverse=True)
    out = out[:limit]

    # Only the shortlist gets the slow name lookup.
    if funds:
        for r in out:
            if not r["name"]:
                r["name"] = fund_name(r["symbol"])
        for r in out:
            r.update(_plan_flags(r["name"]))

    for r in out:
        r.pop("_score", None)
    return out


def _plan_flags(name: str) -> dict:
    """Label Indian fund share-class conventions from the scheme name.

    Direct plans skip distributor commission and so carry a lower expense ratio
    than Regular; Growth reinvests rather than paying income out. Direct+Growth
    is the usual choice for a long-term SIP, and the names differ by two words,
    so surfacing this prevents picking the costlier twin by accident.
    """
    low = (name or "").lower()
    plan = "Direct" if re.search(r"\bdir\b|\bdirect\b", low) else (
        "Regular" if re.search(r"\breg\b|\bregular\b", low) else "")
    option = "Growth" if re.search(r"\bgr\b|\bgrowth\b", low) else (
        "IDCW" if "idcw" in low or "dividend" in low else "")
    return {"plan": plan, "option": option,
            "preferred": plan == "Direct" and option == "Growth"}


def _probe_compacted(raw: str) -> list[dict]:
    """Try the input with spaces stripped, bare and with Indian suffixes.

    Recovers cases like "power india" -> POWERINDIA.NS, which Yahoo's own search
    does not connect. Only symbols that actually return data are kept.
    """
    compact = re.sub(r"[^A-Za-z0-9.^=-]", "", raw).upper()
    if len(compact) < 3:
        return []

    seen: set[str] = set()
    found: list[dict] = []
    for symbol in (compact, f"{compact}.NS", f"{compact}.BO"):
        if symbol in seen or not is_path_safe(symbol):
            continue
        seen.add(symbol)
        if not has_market_data(symbol):
            continue
        # Re-search the confirmed symbol to recover its display name.
        name, exch = "", ""
        for hit in search(symbol, limit=4):
            if hit["symbol"].upper() == symbol:
                name, exch = hit["name"], hit["exchange"]
                break
        found.append({"symbol": symbol, "name": name, "type": "Equity", "exchange": exch})
    return found


def resolve(query: str, limit: int = 8) -> dict:
    """Resolve free-form input to a ticker, or to a list of choices.

    Returns one of:

    ``{"status": "resolved", "symbol": ...}``
        the input is a working ticker, or a search hit matched it so precisely
        that asking would be pedantic (exact symbol match with data behind it);

    ``{"status": "ambiguous", "candidates": [...]}``
        several plausible instruments — the caller should ask the user;

    ``{"status": "not_found", "candidates": []}``
        nothing usable matched.
    """
    raw = (query or "").strip()
    if not raw:
        return {"status": "not_found", "candidates": []}

    upper = raw.upper()

    # Already a usable ticker: run it, no questions asked.
    if is_path_safe(upper) and has_market_data(upper):
        return {"status": "resolved", "symbol": upper}

    candidates = search(raw, limit=limit)

    # Yahoo's search does not match spaced input to a run-together symbol
    # ("power india" misses POWERINDIA), so probe the compacted form directly
    # against the exchanges where that naming style is common.
    if not candidates:
        candidates = _probe_compacted(raw)

    if not candidates:
        return {"status": "not_found", "candidates": []}

    # An exact symbol match that has data is not genuinely ambiguous, even when
    # other hits exist (e.g. "aapl" also matching foreign cross-listings).
    top = candidates[0]
    if top["symbol"].upper() == upper and has_market_data(top["symbol"]):
        return {"status": "resolved", "symbol": top["symbol"]}

    return {"status": "ambiguous", "candidates": candidates}
