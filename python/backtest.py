import sys
import json
import pandas as pd
import numpy as np
import yfinance as yf

# Function to calculate the Relative Strength Index (RSI)
def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period
    rs = gains / losses if losses != 0 else 100
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Function to fetch historical stock data from Yahoo Finance
def fetch_historical_data(symbol, start_date, end_date):
    """
    Fetch historical stock data from Yahoo Finance.
    """
    stock_data = yf.download(symbol, start=start_date, end=end_date)
    stock_data = stock_data[['Close']]  # We're interested in the closing prices
    stock_data.reset_index(inplace=True)  # Reset the index to make 'Date' a column
    return stock_data

# Function to perform backtest dynamically using RSI
def perform_backtest(symbol, strategy, start_date, end_date):
    # Fetch historical price data
    data = fetch_historical_data(symbol, start_date, end_date)
    
    # Calculate RSI (rolling window of 14 days)
    rsi_values = data['Close'].rolling(window=14).apply(lambda x: calculate_rsi(x), raw=False)
    data['RSI'] = rsi_values
    
    # Initialize backtest variables
    initial_balance = 10000  # Starting with $10,000
    balance = initial_balance
    positions = []  # To track open trades
    profits = []  # To track profits from each closed trade
    
    for i in range(1, len(data)):
        # Strategy: Buy when RSI < 30, Sell when RSI > 70
        if data['RSI'].iloc[i] < 30 and balance > data['Close'].iloc[i]:
            # Buy signal: Buy 1 unit of the stock at the current price
            balance -= data['Close'].iloc[i]
            positions.append(data['Close'].iloc[i])  # Store buy price
            print(f"Buy at {data['Date'].iloc[i]}: {data['Close'].iloc[i]}")
        
        elif data['RSI'].iloc[i] > 70 and len(positions) > 0:
            # Sell signal: Sell 1 unit of stock at the current price
            buy_price = positions.pop()
            profit = data['Close'].iloc[i] - buy_price
            balance += data['Close'].iloc[i]
            profits.append(profit)
            print(f"Sell at {data['Date'].iloc[i]}: {data['Close'].iloc[i]} - Profit: {profit}")
    
    # Calculate results
    total_profit = sum(profits)
    win_trades = len([p for p in profits if p > 0])
    total_trades = len(profits)
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0

    # Calculate Max Drawdown
    portfolio_values = [initial_balance + sum(profits[:i+1]) for i in range(len(profits))]
    max_drawdown = (max(portfolio_values) - min(portfolio_values)) / max(portfolio_values) * 100 if len(portfolio_values) > 0 else 0

    # Calculate Sharpe Ratio (simplified: average return / std deviation of returns)
    returns = np.diff([initial_balance + sum(profits[:i+1]) for i in range(len(profits))])  # Calculate returns from portfolio values
    if len(returns) > 0:
        average_return = np.mean(returns)
        volatility = np.std(returns)
        sharpe_ratio = average_return / volatility if volatility != 0 else 0
    else:
        sharpe_ratio = 0
    
    return {
        "profit": round(total_profit, 2),
        "winRate": round(win_rate, 2),
        "maxDrawdown": round(max_drawdown, 2),
        "sharpeRatio": round(sharpe_ratio, 2)
    }

def main():
    # Get the stock symbol and strategy from the arguments
    if len(sys.argv) != 5:
        print(json.dumps({"success": False, "error": "Missing arguments. Expected symbol, strategy, start_date, and end_date."}))
        return
    
    symbol = sys.argv[1]
    strategy = sys.argv[2]  # Not currently used, but can be extended for different strategies
    start_date = sys.argv[3]
    end_date = sys.argv[4]
    print(f"Performing backtest for {symbol} using strategy {strategy} from {start_date} to {end_date}...")
    # Perform the backtest dynamically
    results = perform_backtest(symbol, strategy, start_date, end_date)

    # Return results as JSON
    print(json.dumps(results))

if __name__ == "__main__":
    main()
