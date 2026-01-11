import yfinance as yf
import matplotlib.pyplot as plt
import os
import io
import base64
import pandas as pd

def generate_chart(symbol):
    """
    Generates a chart for the given symbol and returns a base64 image string.
    Ensures the data is 1D and handles empty/malformed data gracefully.
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

    # --- Validate 'Close' column ---
    if data.empty or "Close" not in data.columns:
        print(f"⚠️ No valid 'Close' data for {symbol}")
        return None

    # --- Force 1D numpy array ---
    y = data["Close"].to_numpy().ravel()  # ensures 1D even if 2D
    x = data.index
    if len(y) == 0:
        print(f"⚠️ 'Close' data is empty for {symbol}")
        return None

    # --- Ensure timezone-naive index for matplotlib ---
    if isinstance(x, pd.DatetimeIndex) and x.tz is not None:
        x = x.tz_convert(None)

    # --- Plot ---
    plt.figure(figsize=(7, 4), facecolor="#020617")
    ax = plt.gca()
    ax.set_facecolor("#020617")

    # Line plot
    plt.plot(x, y, color="#22c55e", linewidth=2, label="Close Price")

    # Gradient fill
    plt.fill_between(x, y, y.min(), color="#22c55e", alpha=0.15)

    # Title & labels
    plt.title(symbol, color="white", fontsize=14, pad=10)
    plt.xlabel("Time", color="#94a3b8")
    plt.ylabel("Price", color="#94a3b8")
    plt.xticks(color="#94a3b8", rotation=45)
    plt.yticks(color="#94a3b8")
    for spine in ax.spines.values():
        spine.set_visible(False)
    plt.grid(alpha=0.1)
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
