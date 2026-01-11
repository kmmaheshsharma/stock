import yfinance as yf
import matplotlib.pyplot as plt
import os
import io
import base64
import pandas as pd

def generate_chart(symbol):
    """
    Generates a fancy chart for the given symbol and returns base64 image string.
    Handles timezone-aware index and missing data gracefully.
    """
    # --- Chart folder ---
    chart_dir = os.path.join(os.getcwd(), "chart")
    os.makedirs(chart_dir, exist_ok=True)

    # --- Fetch data ---
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

    # --- Ensure index is timezone-naive for matplotlib ---
    if isinstance(data.index, pd.DatetimeIndex) and data.index.tz is not None:
        data.index = data.index.tz_convert(None)

    # --- Plot ---
    plt.figure(figsize=(7, 4), facecolor="#020617")
    ax = plt.gca()
    ax.set_facecolor("#020617")

    # Line plot
    plt.plot(data.index, data["Close"], color="#22c55e", linewidth=2, label="Close Price")

    # Gradient fill
    plt.fill_between(
        data.index,
        data["Close"],
        data["Close"].min(),
        color="#22c55e",
        alpha=0.15
    )

    # Title & labels
    plt.title(symbol, color="white", fontsize=14, pad=10)
    plt.xlabel("Time", color="#94a3b8")
    plt.ylabel("Price", color="#94a3b8")

    plt.xticks(color="#94a3b8", rotation=45)
    plt.yticks(color="#94a3b8")

    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.grid(alpha=0.1)

    # Tight layout
    plt.tight_layout()

    # Save locally (optional)
    chart_path = os.path.join(chart_dir, f"{symbol}.png")
    plt.savefig(chart_path, bbox_inches="tight", facecolor="#020617")

    # Convert to base64
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="#020617")
    plt.close()
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")

    return f"data:image/png;base64,{img_base64}"
