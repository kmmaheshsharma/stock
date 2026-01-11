import yfinance as yf
import matplotlib.pyplot as plt
import os
import io
import base64
import pandas as pd
from datetime import time

def generate_chart(symbol):
    chart_dir = os.path.join(os.getcwd(), "chart")
    os.makedirs(chart_dir, exist_ok=True)

    # Fetch data
    try:
        data = yf.download(
            symbol,
            period="5d",
            interval="15m",
            progress=False,
            auto_adjust=True
        )
    except Exception as e:
        print(f"❌ Error fetching {symbol}: {e}")
        return None

    if data.empty or "Close" not in data.columns:
        print(f"⚠️ No valid 'Close' data for {symbol}")
        return None

    # Ensure 1D array
    y = data["Close"].to_numpy().ravel()
    x = data.index
    if len(y) == 0:
        print(f"⚠️ 'Close' data is empty for {symbol}")
        return None

    # Timezone-naive for plotting
    if isinstance(x, pd.DatetimeIndex) and x.tz is not None:
        x = x.tz_convert(None)

    # --- Plot ---
    plt.figure(figsize=(7, 4), facecolor="#020617")
    ax = plt.gca()
    ax.set_facecolor("#020617")
    
    # Line plot
    plt.plot(x, y, color="#22c55e", linewidth=2, label="Close Price")
    plt.fill_between(x, y, y.min(), color="#22c55e", alpha=0.15)

    # Dynamic Market Open/Close Shading (for each day)
    unique_dates = pd.to_datetime(x.date).unique()
    for d in unique_dates:
        day_start = pd.Timestamp.combine(d, time(9, 15))
        day_end = pd.Timestamp.combine(d, time(15, 30))
        plt.axvspan(day_start, day_end, color="#ffffff", alpha=0.02)

    # Labels & style
    plt.title(symbol, color="white", fontsize=14, pad=10)
    plt.xlabel("Time", color="#94a3b8")
    plt.ylabel("Price", color="#94a3b8")
    plt.xticks(color="#94a3b8", rotation=45)
    plt.yticks(color="#94a3b8")
    for spine in ax.spines.values():
        spine.set_visible(False)
    plt.grid(alpha=0.1)
    plt.tight_layout()

    # Save locally
    chart_path = os.path.join(chart_dir, f"{symbol}.png")
    plt.savefig(chart_path, bbox_inches="tight", facecolor="#020617")

    # Convert to base64
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="#020617")
    plt.close()
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")

    return f"data:image/png;base64,{img_base64}"
