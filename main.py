from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# DEFAULT_CONFIG already applies TRADINGAGENTS_* env-var overrides
# (llm_provider, deep_think_llm, quick_think_llm, backend_url, etc.),
# so users can switch models or endpoints purely via .env without
# editing this script. Override individual keys here only when you
# want a hard-coded value that should ignore the environment.
config = DEFAULT_CONFIG.copy()

# Optional: once ALPHA_VANTAGE_API_KEY is set in .env, uncomment this to add
# Alpha Vantage as a news fallback. Its NEWS_SENTIMENT endpoint supplies real
# sentiment scores — the best free substitute for the StockTwits feed (now
# OAuth-only) and the anonymous Reddit RSS feed (IP rate-limited).
# yfinance stays first, so Alpha Vantage's 25 requests/day are only spent when
# yfinance comes back empty.
# config["data_vendors"] = {**config["data_vendors"], "news_data": "yfinance,alpha_vantage"}


# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
