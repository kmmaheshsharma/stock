import sys
import json
import pandas as pd
import numpy as np
import yfinance as yf

# Function to calculate the Relative Strength Index (RSI)
def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return np.array([])  # Return empty array if not enough data
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        rsi = np.ones(len(prices)) * 100  # RSI = 100 when no losses
    else:
        rsi = []
        for i in range(period, len(prices)):
            gain = gains[i]
            loss = losses[i]

            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

            rs = avg_gain / avg_loss if avg_loss != 0 else 100
            rsi_value = 100 - (100 / (1 + rs))
            rsi.append(rsi_value)

    rsi = [np.nan] * period + rsi
    return np.array(rsi)

# Function to fetch historical stock data from Yahoo Finance
def fetch_historical_data(symbol, start_date, end_date):
    try:
        stock_data = yf.download(symbol, start=start_date, end=end_date)
        stock_data = stock_data[['Close']]  # We're interested in the closing prices
        stock_data.reset_index(inplace=True)  # Reset the index to make 'Date' a column
        return stock_data
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()  # Return empty DataFrame on error

# Function to perform backtest dynamically using RSI
def perform_backtest(symbol, strategy, start_date, end_date):
    data = fetch_historical_data(symbol, start_date, end_date)

    if data.empty or len(data) < 14:
        print(f"Not enough data to perform backtest for {symbol} from {start_date} to {end_date}")
        return json.dumps({
            "profit": 0.0,
            "winRate": 0.0,
            "maxDrawdown": 0.0,
            "sharpeRatio": 0.0
        })

    rsi_values = calculate_rsi(data['Close'].values, period=14)
    if rsi_values.size == 0:
        return json.dumps({
            "profit": 0.0,
            "winRate": 0.0,
            "maxDrawdown": 0.0,
            "sharpeRatio": 0.0
        })

    data['RSI'] = rsi_values
    initial_balance = 10000
    balance = initial_balance
    positions = []  # To track open trades
    profits = []  # To track profits from each closed trade

    for i in range(1, len(data)):
        if data['RSI'].iloc[i] < 30 and balance > data['Close'].iloc[i]:
            balance -= data['Close'].iloc[i]
            positions.append(data['Close'].iloc[i])  # Store buy price
            print(f"Buy at {data['Date'].iloc[i]}: {data['Close'].iloc[i]}")
        
        elif data['RSI'].iloc[i] > 70 and len(positions) > 0:
            buy_price = positions.pop()
            profit = data['Close'].iloc[i] - buy_price
            balance += data['Close'].iloc[i]
            profits.append(profit)
            print(f"Sell at {data['Date'].iloc[i]}: {data['Close'].iloc[i]} - Profit: {profit}")
    
    total_profit = sum(profits)
    win_trades = len([p for p in profits if p > 0])
    total_trades = len(profits)
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0

    portfolio_values = [initial_balance + sum(profits[:i+1]) for i in range(len(profits))]
    max_drawdown = (max(portfolio_values) - min(portfolio_values)) / max(portfolio_values) * 100 if len(portfolio_values) > 0 else 0

    returns = np.diff([initial_balance + sum(profits[:i+1]) for i in range(len(profits))])  
    if len(returns) > 0:
        average_return = np.mean(returns)
        volatility = np.std(returns)
        sharpe_ratio = average_return / volatility if volatility != 0 else 0
    else:
        sharpe_ratio = 0
    
    result = {
        "profit": round(total_profit, 2),
        "winRate": round(win_rate, 2),
        "maxDrawdown": round(max_drawdown, 2),
        "sharpeRatio": round(sharpe_ratio, 2)
    }
    print(f"Backtest result for {symbol} from {start_date} to {end_date}: {result}")
    return json.dumps(result)

def main():
    if len(sys.argv) != 5:
        print(json.dumps({"success": False, "error": "Missing arguments. Expected symbol, strategy, start_date, and end_date."}))
        return
    
    symbol = sys.argv[1]
    strategy = sys.argv[2]
    start_date = sys.argv[3]
    end_date = sys.argv[4]

    print(f"Performing backtest for {symbol} using strategy {strategy} from {start_date} to {end_date}...")
    results = perform_backtest(symbol, strategy, start_date, end_date)

    print(results)

if __name__ == "__main__":
    main()
