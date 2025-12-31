import yfinance as yf

def get_price(symbol):
    """
    Returns:
        price (float): Latest close price
        low (float): Low of the day
        high (float): High of the day
        volume (int): Latest volume
        avg_volume (float): Average volume of the day
        change_percent (float): % change from previous close
    """
    ticker = yf.Ticker(symbol + ".NS")
    hist = ticker.history(period="1d", interval="5m")

    if hist.empty:
        return None, None, None, None, None, None

    # Latest row
    latest = hist.iloc[-1]
    price = latest["Close"]
    volume = latest["Volume"]

    # Day stats
    day_low = hist["Low"].min()
    day_high = hist["High"].max()
    avg_volume = hist["Volume"].mean()

    # Previous close to calculate % change
    prev_close = hist["Close"].iloc[0]  # first value of the day
    change_percent = ((price - prev_close) / prev_close) * 100 if prev_close else 0

    return price, day_low, day_high, volume, avg_volume, change_percent
