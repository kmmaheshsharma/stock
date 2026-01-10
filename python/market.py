import yfinance as yf
import pandas as pd
import logging
from alpha_vantage.timeseries import TimeSeries

# Set up logging for better debugging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

# Alpha Vantage API Key (you need to sign up and get your API key from Alpha Vantage)
ALPHA_VANTAGE_API_KEY = 'QJVIKMT22FGUEGZS'

def get_price(symbol):
    """
    symbol can be:
    - "SBIN.NS"
    - "SBIN.BO"
    - ["SBIN.NS", "SBIN.BO"]  (recommended)
    """

    symbols = symbol if isinstance(symbol, list) else [symbol]

    for sym in symbols:
        # First, try fetching data from Yahoo Finance
        result = get_price_from_yahoo(sym)
        if result:
            return result

        # If Yahoo Finance fails, try Alpha Vantage as a fallback        
        result = get_price_from_alpha_vantage(sym)
        if result:
            return result

    logging.error(f"No valid data found for any of the symbols: {symbols}")
    return None

def get_price_from_yahoo(symbol):
    try:
        ticker = yf.Ticker(symbol)

        # Fetch 5-day data (1-day interval)
        data = ticker.history(period="5d", interval="1d")

        if data is None or data.empty:
            logging.warning(f"No data found for {symbol} from Yahoo Finance.")
            return None

        data = data.dropna(how="all")
        if data.empty:
            logging.warning(f"Data is empty for {symbol}.")
            return None

        last = data.iloc[-1]

        close = last.get("Close")
        open_ = last.get("Open")
        low = last.get("Low")
        high = last.get("High")
        volume = last.get("Volume")

        # Core validations
        if pd.isna(close):
            logging.warning(f"Close price is missing for {symbol}.")
            return None

        # Convert to float and handle missing values
        price = float(close)
        low = float(low) if not pd.isna(low) else None
        high = float(high) if not pd.isna(high) else None
        volume = int(volume) if not pd.isna(volume) else 0

        # Average volume (safe)
        vol_series = data["Volume"].dropna()
        avg_volume = int(vol_series.mean()) if not vol_series.empty else 0

        # Change percentage calculation
        if open_ and not pd.isna(open_) and open_ > 0:
            change_percent = round(((price - open_) / open_) * 100, 2)
        else:
            change_percent = 0.0

        return {
            "symbol": symbol,
            "price": price,
            "low": low,
            "high": high,
            "volume": volume,
            "avg_volume": avg_volume,
            "change_percent": change_percent,
            "source": "yahoo"
        }

    except Exception as e:
        logging.error(f"Error fetching data for {symbol} from Yahoo Finance: {str(e)}")
        return None

def get_price_from_alpha_vantage(symbol):
    try:
        ts = TimeSeries(key=ALPHA_VANTAGE_API_KEY, output_format='pandas')

        # Fetch the quote data for the symbol
        data, metadata = ts.get_quote_endpoint(symbol=symbol)

        if data.empty:
            logging.warning(f"No data found for {symbol} from Alpha Vantage.")
            return None

        # Extract the required fields from the response
        price = data['05. price'][0]  # Latest closing price
        low = data['04. low'][0]  # Low
        high = data['03. high'][0]  # High
        volume = data['06. volume'][0]  # Volume

        # Calculate the change percentage based on the open and close prices
        open_ = data['02. open'][0]
        if open_ > 0:
            change_percent = round(((price - open_) / open_) * 100, 2)
        else:
            change_percent = 0.0

        return {
            "symbol": symbol,
            "price": price,
            "low": low,
            "high": high,
            "volume": volume,
            "avg_volume": 0,  # Alpha Vantage doesn't provide average volume directly
            "change_percent": change_percent,
            "source": "alpha_vantage"
        }

    except Exception as e:
        logging.error(f"Error fetching data for {symbol} from Alpha Vantage: {str(e)}")
        return None
