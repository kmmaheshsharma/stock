import pandas as pd

def safe_float(x, default=0.0):
    """Convert to float, fallback to default if invalid."""
    try:
        if x is None or pd.isna(x):
            return default
        return float(x)
    except (ValueError, TypeError):
        return default

def calculate_indicators_from_price(price_data):
    """
    Calculate EMA20, EMA50, RSI, MACD from single price_data dict.
    Returns JSON-safe dictionary.
    """
    price = safe_float(price_data.get("price"), default=0.0)

    # Create temp DataFrame with Close price
    temp_df = pd.DataFrame({"Close": [price]})

    close = temp_df['Close']

    # EMA
    ema20 = close.ewm(span=20, adjust=False).mean().iat[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iat[-1]

    # RSI
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(14, min_periods=1).mean()  # min_periods=1 to avoid NaN
    avg_loss = down.rolling(14, min_periods=1).mean()
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.iat[-1]

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # JSON-safe rounding
    def round_safe(x, default=0.0, ndigits=4):
        try:
            if pd.isna(x):
                return default
            return round(float(x), ndigits)
        except (ValueError, TypeError):
            return default

    return {
        "ema20": round_safe(ema20),
        "ema50": round_safe(ema50),
        "rsi": round_safe(rsi_val),
        "macd": {
            "value": round_safe(macd_line.iat[-1]),
            "signal": round_safe(macd_signal.iat[-1]),
            "histogram": round_safe(macd_hist.iat[-1])
        }
    }

# ===== Example usage =====
if __name__ == "__main__":
    price_data_example = {"price": 435.5, "low": 430, "high": 440, "volume": 10000}
    indicators = calculate_indicators_from_price(price_data_example)
    print(indicators)
