import sys
import json
import argparse
import re

from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart


def normalize_symbol(raw: str) -> str:
    """
    Extract clean NSE symbol and ensure SINGLE .NS suffix
    """
    raw = raw.upper().strip()

    # Extract base symbol (letters only, before any junk)
    match = re.match(r"([A-Z]{2,15})(?:\.NS)?", raw)
    if not match:
        raise ValueError(f"Invalid symbol received: {raw}")

    symbol = match.group(1)

    return symbol + ".NS"

# ---------- Core Engine ----------
def run_engine(symbol, entry_price=None):
    try:
        symbol = normalize_symbol(symbol)

        price, low, high, volume, avg_volume, change_percent = get_price(symbol)

        alerts = []

        if price is None:
            return {
                "symbol": symbol,
                "error": f"No price data found for {symbol}",
                "alerts": ["invalid_symbol"]
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

        suggested_entry = None
        if low and high:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

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
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--entry", type=float)

    args = parser.parse_args()

    result = run_engine(args.symbol, args.entry)

    # Always valid JSON
    print(json.dumps(result, ensure_ascii=False))
