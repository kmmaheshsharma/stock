import yfinance as yf
import matplotlib.pyplot as plt
import os
import io
import base64

def generate_chart(symbol):
    chart_dir = os.path.join(os.getcwd(), "chart")
    if not os.path.exists(chart_dir):
        os.makedirs(chart_dir)

    data = yf.download(
        symbol,
        period="5d",
        interval="15m",
        progress=False,
        auto_adjust=True
    )

    if data.empty:
        return None

    plt.figure(figsize=(7, 4), facecolor="#020617")
    ax = plt.gca()
    ax.set_facecolor("#020617")

    # Line
    plt.plot(data.index, data["Close"], color="#22c55e", linewidth=2)

    # Gradient fill
    plt.fill_between(
        data.index,
        data["Close"],
        min(data["Close"]),
        color="#22c55e",
        alpha=0.15
    )

    plt.title(symbol, color="white", fontsize=14, pad=10)
    plt.xlabel("Time", color="#94a3b8")
    plt.ylabel("Price", color="#94a3b8")

    plt.xticks(color="#94a3b8")
    plt.yticks(color="#94a3b8")

    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.grid(alpha=0.1)

    # Save local (optional)
    chart_path = os.path.join(chart_dir, f"{symbol}.png")
    plt.savefig(chart_path, bbox_inches="tight", facecolor="#020617")

    # Convert to base64
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="#020617")
    plt.close()
    buf.seek(0)

    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"
