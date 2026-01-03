import yfinance as yf
import matplotlib.pyplot as plt
import os


def generate_chart(symbol):
    """
    symbol is already normalized (e.g. KPIGREEN.NS)
    """

    # --- Create chart folder if it doesn't exist ---
    chart_dir = os.path.join(os.getcwd(), "chart")
    if not os.path.exists(chart_dir):
        os.makedirs(chart_dir)

    # ❌ DO NOT append .NS here
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
    plt.plot(data.index, data["Close"])
    plt.title(symbol)
    plt.grid(True)

    # Save chart
    chart_path = os.path.join(chart_dir, f"{symbol}.png")
    plt.savefig(chart_path)
    plt.close()

    return chart_path
