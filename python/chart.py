import yfinance as yf
import matplotlib.pyplot as plt
import os

def generate_chart(symbol):
    # --- Create chart folder if it doesn't exist ---
    chart_dir = os.path.join(os.getcwd(), "chart")
    if not os.path.exists(chart_dir):
        os.makedirs(chart_dir)

    # Disable yfinance progress output
    data = yf.download(
        symbol + ".NS",
        period="5d",
        interval="15m",
        progress=False,    # disable [****100%****] bar
        auto_adjust=True
    )

    # Plot chart
    plt.figure(figsize=(6,4))
    plt.plot(data["Close"])
    plt.title(symbol)

    # Save chart inside chart folder
    chart_path = os.path.join(chart_dir, f"{symbol}.png")
    plt.savefig(chart_path)
    plt.close()
    
    return chart_path
