import yfinance as yf

def get_price(symbol):
    """
    symbol is ALREADY normalized (e.g. KPIGREEN.NS)
    """

    ticker = yf.Ticker(symbol)
    data = ticker.history(period="1d")

    if data.empty:
        return None, None, None, None, None, None

    price = float(data["Close"].iloc[-1])
    low = float(data["Low"].iloc[-1])
    high = float(data["High"].iloc[-1])
    volume = int(data["Volume"].iloc[-1])

    avg_volume = int(data["Volume"].tail(10).mean())
    change_percent = round(
        ((price - data["Open"].iloc[-1]) / data["Open"].iloc[-1]) * 100,
        2
    )

    return price, low, high, volume, avg_volume, change_percent
