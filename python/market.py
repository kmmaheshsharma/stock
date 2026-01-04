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

            # 5d avoids holiday / no-trade issues
            data = ticker.history(period="5d", interval="1d")

            if data is None or data.empty:
                continue

            data = data.dropna(how="all")
            if data.empty:
                continue

            last = data.iloc[-1]

            close = last.get("Close")
            open_ = last.get("Open")
            low = last.get("Low")
            high = last.get("High")
            volume = last.get("Volume")

            # Core validations
            if pd.isna(close):
                continue

            price = float(close)
            low = float(low) if not pd.isna(low) else None
            high = float(high) if not pd.isna(high) else None
            volume = int(volume) if not pd.isna(volume) else 0

            # Avg volume (safe)
            vol_series = data["Volume"].dropna()
            avg_volume = int(vol_series.mean()) if not vol_series.empty else 0

            # Change % (safe)
            if open_ and not pd.isna(open_) and open_ > 0:
                change_percent = round(((price - open_) / open_) * 100, 2)
            else:
                change_percent = 0.0

            return {
                "symbol": sym,
                "price": price,
                "low": low,
                "high": high,
                "volume": volume,
                "avg_volume": avg_volume,
                "change_percent": change_percent,
                "source": "yahoo"
            }

        except Exception as e:
            # silently try next exchange
            continue

    return None
