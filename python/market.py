import yfinance as yf
import pandas as pd

def get_price(symbol):
    """
    symbol can be:
    - "SBIN.NS"
    - "SBIN.BO"
    - ["SBIN.NS", "SBIN.BO"]  (recommended)
    """

    symbols = symbol if isinstance(symbol, list) else [symbol]

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)

            # Use 5d to avoid holiday / no-trade issues
            data = ticker.history(period="5d", interval="1d")

            if data is None or data.empty:
                continue

            # Pick the last valid trading day
            data = data.dropna()
            if data.empty:
                continue

            last = data.iloc[-1]

            price = float(last["Close"])
            low = float(last["Low"])
            high = float(last["High"])
            volume = int(last["Volume"])

            avg_volume = int(data["Volume"].tail(10).mean())
            change_percent = round(
                ((last["Close"] - last["Open"]) / last["Open"]) * 100,
                2
            )

            return {
                "symbol": sym,
                "price": price,
                "low": low,
                "high": high,
                "volume": volume,
                "avg_volume": avg_volume,
                "change_percent": change_percent
            }

        except Exception:
            continue

    # Nothing worked
    return None
