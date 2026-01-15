import yfinance as yf
import pandas as pd
import numpy as np

def fetch_price_data(symbols, period="60d"):
    """
    Try multiple symbols until valid price data is found.
    Returns the first valid DataFrame or None.
    """
    for sym in symbols:
        try:
            data = yf.download(sym, period=period, progress=False)
            if not data.empty:
                return data
        except Exception as e:
            print(f"Error fetching {sym}: {e}")
    return None


def calculate_indicators(data):
    """
    Given a DataFrame with 'Close' prices, compute EMA20, EMA50, RSI, MACD.
    Returns a dictionary with rounded float values.
    """
    close = data['Close']

    # EMA
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

    # RSI
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(14).mean()
    avg_loss = down.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.iloc[-1]

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    return {
        "ema20": round(float(ema20), 2),
        "ema50": round(float(ema50), 2),
        "rsi": round(float(rsi_val), 2),
        "macd": {
            "value": round(float(macd_line.iloc[-1]), 4),
            "signal": round(float(macd_signal.iloc[-1]), 4),
            "histogram": round(float(macd_hist.iloc[-1]), 4)
        }
    }


def get_indicators_for_symbol(normalized_symbols):
    """
    Main helper to fetch price data and compute indicators.
    Returns a dictionary or None if no valid data is found.
    """
    data = fetch_price_data(normalized_symbols)
    if data is None:
        print(f"WARNING: No valid price data for symbols: {normalized_symbols}")
        return None

    indicators = calculate_indicators(data)
    return indicators


# Example usage:
if __name__ == "__main__":
    symbols = ["IFL.NS", "IFL.BO", "IFL.US"]
    indicators = get_indicators_for_symbol(symbols)
    if indicators:
        print(indicators)
    else:
        print("No indicators could be calculated.")
