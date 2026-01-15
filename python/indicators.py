import pandas as pd
import numpy as np

def calculate_indicators(data):
    """
    Calculate EMA20, EMA50, RSI, and MACD from a DataFrame with 'Close'.
    Ensures all returned values are valid floats for JSON (no NaN/None).
    """
    # Default values if data is missing
    defaults = {
        "ema20": 0.0,
        "ema50": 0.0,
        "rsi": 50.0,
        "macd": {"value": 0.0, "signal": 0.0, "histogram": 0.0}
    }

    if data is None or data.empty or 'Close' not in data.columns:
        return defaults

    close = data['Close']

    # Ensure series is numeric
    close = pd.to_numeric(close, errors='coerce').fillna(method='ffill').fillna(0.0)

    # EMA
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    # RSI
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(14, min_periods=1).mean()
    avg_loss = down.rolling(14, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.fillna(50.0)  # default neutral if division by zero

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # Helper to safely convert last value to JSON-safe float
    def safe_float(series, default=0.0):
        try:
            val = float(series.iat[-1])
            if np.isnan(val):
                return default
            return round(val, 4)
        except:
            return default

    return {
        "ema20": safe_float(ema20),
        "ema50": safe_float(ema50),
        "rsi": safe_float(rsi_val, default=50.0),
        "macd": {
            "value": safe_float(macd_line),
            "signal": safe_float(macd_signal),
            "histogram": safe_float(macd_hist)
        }
    }
