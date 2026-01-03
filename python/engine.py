import sys
import json
import argparse

from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart


# ---------- Helpers ----------
def normalize_symbol(symbol: str) -> str:
    """
    Ensure clean NSE symbol (no flags, no commas)
    """
    symbol = symbol.upper().strip()

    # Safety: remove anything except letters/numbers
    symbol = "".join(c for c in symbol if c.isalnum())

    # Append .NS if missing
    if not symbol.endswith(".NS"):
        symbol = symbol + ".NS"

    return symbol


# ---------- Core Engine ----------
def run_engine(symbol, entry_price=None):
    try:
        symbol = normalize_symbol(symbol)

        # Fetch price and stats
        price, low, high, volume, avg_volume, change_percent = get_price(symbol)

        alerts = []

        if price is None:
            alerts.append("invalid_symbol")
            return {
                "symbol": symbol,
                "error": f"No price data found for {symbol}",
                "alerts": alerts
            }

        # Price-based alerts
        if entry_price is not None:
            if price > entry_price * 1.05:
                alerts.append("profit")
            elif price < entry_price * 0.95:
                alerts.append("loss")

        # Sentiment
        sentiment_score, s_type = sentiment_for_symbol(symbol)
        if s_type == "accumulation":
            alerts.append("buy_signal")
        elif s_type == "hype":
            alerts.append("trap_warning")

        # Suggested entry zone
        suggested_entry = None
        if low and high:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

        # Generate chart as base64
        chart_base64 = generate_chart(symbol)

        return {
            "symbol": symbol,
            "price": price,
            "low": low,
            "high": high,
            "volume": volume,
            "avg_volume": avg_volume,
            "change_percent": change_percent,
            "sentiment": sentiment_score,
            "sentiment_type": s_type,
            "alerts": alerts,
            "suggested_entry": suggested_entry,
            "chart": chart_base64
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": str(e),
            "alerts": ["error"]
        }


# ---------- Entry Point ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock analysis engine")
    parser.add_argument("symbol", help="Stock symbol (e.g. KPIGREEN)")
    parser.add_argument("--entry", type=float, default=None)

    args = parser.parse_args()

    result = run_engine(args.symbol, args.entry)

    # Always output valid JSON
    print(json.dumps(result, ensure_ascii=False))
