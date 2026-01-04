import sys
import json
import argparse
import re

from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart


def normalize_symbol(raw: str):
    """
    Extract ONLY the base stock symbol from user input
    Supports NSE & BSE
    """

    raw = raw.upper().strip()

    # Remove common command words
    raw = re.sub(r"\b(TRACK|ENTRY|BUY|SELL|ADD|SHOW|PRICE)\b", "", raw)

    # Replace separators
    raw = raw.replace("-", " ").replace("_", " ")

    # Extract first valid symbol token
    match = re.search(r"\b[A-Z&]{2,15}\b", raw)
    if not match:
        raise ValueError(f"Invalid symbol received: {raw}")

    base = match.group(0)

    return [
        f"{base}.NS",
        f"{base}.BO"
    ]

# ---------- Core Engine ----------
def run_engine(symbol, entry_price=None):
    try:
        symbols = normalize_symbol(symbol)

        price_data = get_price(symbols)

        if not price_data:
            return {
                "symbol": symbols,
                "error": "No price data found",
                "alerts": ["error"]
            }

        price = price_data["price"]
        low = price_data["low"]
        high = price_data["high"]
        volume = price_data["volume"]
        avg_volume = price_data["avg_volume"]
        change_percent = price_data["change_percent"]

        alerts = []

        if entry_price:
            if price > entry_price * 1.05:
                alerts.append("profit")
            elif price < entry_price * 0.95:
                alerts.append("loss")

        sentiment_score, s_type = sentiment_for_symbol(price_data["symbol"])

        if s_type == "accumulation":
            alerts.append("buy_signal")
        elif s_type == "hype":
            alerts.append("trap_warning")

        suggested_entry = None
        if low and high:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

        chart_base64 = generate_chart(price_data["symbol"])

        return {
            "symbol": price_data["symbol"],
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
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--entry", type=float)

    args = parser.parse_args()

    result = run_engine(args.symbol, args.entry)

    # Always valid JSON
    print(json.dumps(result, ensure_ascii=False))
