import yfinance as yf
import matplotlib.pyplot as plt
import os
import io
import base64

def generate_chart(symbol):
    """
    symbol is already normalized (e.g. KPIGREEN.NS)
    Returns a base64 string of the chart (suitable for embedding in HTML <img> src)
    """

    # --- Create chart folder if needed ---
    chart_dir = os.path.join(os.getcwd(), "chart")
    if not os.path.exists(chart_dir):
        os.makedirs(chart_dir)

    # Fetch data
    data = yf.download(
        symbol,
        period="5d",
        interval="15m",
        progress=False,
        auto_adjust=True
    )

    if data.empty:
        return None

    # Plot chart
    plt.figure(figsize=(6, 4))
    plt.plot(data.index, data["Close"], label="Close Price")
    plt.title(symbol)
    plt.grid(True)
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.legend()

    # Save chart locally (optional)
    chart_path = os.path.join(chart_dir, f"{symbol}.png")
    plt.savefig(chart_path)
    
    # Convert chart to base64
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"
