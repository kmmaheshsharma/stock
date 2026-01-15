import yfinance as yf
import pandas as pd
def get_ohlc(symbol, period="3mo", interval="1d"):
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False
        )
        if df.empty:
            return None
        return df
    except Exception:
        return None

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def macd(series):
    ema12 = ema(series, 12)
    ema26 = ema(series, 26)
    macd_line = ema12 - ema26
    signal = ema(macd_line, 9)
    histogram = macd_line - signal

    return macd_line, signal, histogram
    
def get_indicators(symbol):
    df = get_ohlc(symbol)

    if df is None or len(df) < 50:
        return None

    close = df["Close"]

    ema20 = ema(close, 20).iloc[-1]
    ema50 = ema(close, 50).iloc[-1]

    rsi_val = rsi(close).iloc[-1]

    macd_line, macd_signal, macd_hist = macd(close)

    return {
        "ema20": round(float(ema20), 2),
        "ema50": round(float(ema50), 2),
        "rsi": round(float(rsi_val), 2),
        "macd": {
            "value": round(float(macd_line.iloc[-1]), 4),
            "signal": round(float(macd_signal.iloc[-1]), 4),
            "histogram": round(float(macd_hist.iloc[-1]), 4),
        }
    }
