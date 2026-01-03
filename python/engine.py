import sys
import json
import argparse
import re
import yfinance as yf  # Import yfinance for fetching stock data

from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart


def normalize_symbol(raw: str) -> str:
    """
    Extract clean NSE symbol and ensure SINGLE .NS suffix
    """
    raw = raw.upper().strip()
    match = re.match(r"([A-Z]{2,15})(?:\.NS)?", raw)
    if not match:
        raise ValueError(f"Invalid symbol received: {raw}")
    symbol = match.group(1)
    return symbol + ".NS"


def get_technical_indicators(symbol):
    """
    Returns (MA50, MA200, RSI) for the given symbol
    """
    try:
        # Fetch historical price data
        prices = get_historical_prices(symbol)  # list of closing prices
        if len(prices) < 200:  # Ensure we have enough data for MA200
            raise ValueError(f"Not enough price data for {symbol} to calculate technical indicators")

        ma50 = round(sum(prices[-50:]) / 50, 2)
        ma200 = round(sum(prices[-200:]) / 200, 2)

        # Simple RSI calculation
        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
            else:
                losses.append(abs(change))
        avg_gain = sum(gains[-14:]) / 14 if gains else 0
        avg_loss = sum(losses[-14:]) / 14 if losses else 0
        rsi = 100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss != 0 else 100

        return ma50, ma200, round(rsi, 2)
    
    except Exception as e:
        print(f"Error calculating technical indicators for {symbol}: {e}")
        return None, None, None


def get_historical_prices(symbol, period="1y"):
    """
    Returns a list of closing prices for the past 1 year (or specified period)
    """
    symbol = symbol.replace(".NS", "")  # yfinance uses NSE symbols without .NS
    data = yf.download(f"{symbol}.NS", period=period, interval="1d")
    if data.empty:
        return []
    return list(data['Close'])


# ---------- Core Engine ----------
def run_engine(symbol, entry_price=None):
    try:
        symbol = normalize_symbol(symbol)

        # Current price & basic stats
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

        # Suggested entry range
        suggested_entry = None
        if low and high:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

        # Technical indicators (MA50, MA200, RSI)
        moving_average_50, moving_average_200, rsi = get_technical_indicators(symbol)

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
            "moving_average_50": moving_average_50,
            "moving_average_200": moving_average_200,
            "rsi": rsi,
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
