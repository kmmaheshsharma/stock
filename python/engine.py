import sys
import json
from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart  # we will fix this to return base64
import argparse

def run_engine(symbol, entry_price=None):
    try:
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
        if entry_price:
            if price > entry_price * 1.05:
                alerts.append("profit")
            if price < entry_price * 0.95:
                alerts.append("loss")

        # Sentiment
        sentiment_score, s_type = sentiment_for_symbol(symbol)
        if s_type == "accumulation":
            alerts.append("buy_signal")
        if s_type == "hype":
            alerts.append("trap_warning")

        # Suggested entry zone
        suggested_entry = None
        if low and high:
            lower = round(low * 0.99, 2)
            upper = round(low * 1.02, 2)
            suggested_entry = {"lower": lower, "upper": upper}

        # Generate chart as base64 (no disk file)
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", type=str)
    parser.add_argument("--entry", type=float, default=None)
    args = parser.parse_args()

    output = run_engine(args.symbol.upper(), args.entry)
    print(json.dumps(output))  # Always valid JSON
