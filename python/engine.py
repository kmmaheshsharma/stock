import sys
import json
import argparse
import re
import os
import logging
from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart
import requests

# ------------------- Logging Setup -------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ------------------- Groq AI -------------------
from groq import Groq

api_key = os.environ.get("GROQ_API_KEY")
alpha_key = os.environ.get("ALPHA_VANTAGE_KEY")
if not api_key:
    logging.warning("GROQ_API_KEY not found in environment variables.")
groq_client = Groq(api_key=api_key)

# ------------------- Groq Helpers -------------------
def build_groq_prompt_for_symbol(message):
    return f"""
    You are a professional market analyst.

    A user typed the following request:
    '{message}'

    Identify the stock or crypto symbol mentioned in this sentence.
    Return only the exact trading symbol, nothing else.
    Examples:
    - Stocks: AAPL, SBIN.NS, TSLA
    - Crypto: BTC-USD, ETH-USD
    """

def call_groq_ai_symbol(prompt: str, model="openai/gpt-oss-20b", max_tokens=60):
    logging.info("Starting Groq AI call for symbol extraction...")
    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a professional market analyst."},
                {"role": "user", "content": prompt}
            ],
            model=model,
            max_tokens=max_tokens,
            temperature=0
        )

        raw_text = response.choices[0].message.content.strip()
        logging.info(f"Groq AI raw symbol response: {raw_text}")

        if re.match(r'^[A-Z0-9\-]{1,15}(\.[A-Z]{2,10})?$', raw_text):
            return {"symbol": raw_text}
        else:
            logging.warning(f"Invalid symbol format detected: {raw_text}")
            return {"error": "Invalid symbol format", "raw_text": raw_text}

    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e)}

def call_groq_ai(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
    logging.info("Starting Groq AI call for analysis...")
    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a professional market analyst."},
                {"role": "user", "content": prompt}
            ],
            model=model,
            max_tokens=max_tokens,
            temperature=0.3
        )

        raw_text = response.choices[0].message.content
        logging.info("Groq AI response received.")

        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            ai_json = json.loads(match.group(0))
            logging.info("Groq AI JSON parsed successfully.")
            return ai_json

        logging.warning("No JSON found in Groq AI response, returning raw text.")
        return {"error": "Invalid JSON from Groq AI", "raw_text": raw_text}

    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e)}

def build_groq_prompt(symbol, price_data, sentiment_score):
    return f"""
You are a professional financial analyst.

Analyze the following asset (stock or crypto):

Symbol: {symbol}
Current Price: {price_data['price']}
Daily Low: {price_data['low']}
Daily High: {price_data['high']}
Volume: {price_data['volume']}
Average Volume: {price_data['avg_volume']}
Change %: {price_data['change_percent']}
Sentiment Score: {sentiment_score}

Return a JSON object with the following keys:
- predicted_move
- confidence
- support_level
- resistance_level
- risk
- recommendation

Only return valid JSON.
"""

# ------------------- Symbol Normalization -------------------
def normalize_symbol(raw: str):
    raw = raw.upper().strip()
    raw = re.sub(r"\b(TRACK|ENTRY|BUY|SELL|ADD|SHOW|PRICE)\b", "", raw)
    raw = raw.replace("_", " ")

    is_crypto = "-" in raw or raw.endswith("USD") or raw.endswith("USDT") or raw.endswith("BTC")
    if is_crypto:
        symbols = [
            raw.replace(" ", "-") + "-USD",
            raw.replace(" ", "-") + "-USDT",
            raw.replace(" ", "-") + "-BTC"
        ]
    else:
        match = re.search(r"\b[A-Z0-9&]{1,15}\b", raw)
        if not match:
            raise ValueError(f"Invalid symbol received: {raw}")
        base = match.group(0)
        symbols = [
            f"{base}.NS",
            f"{base}.BO",
            base,
            f"{base}.US",
            f"{base}.NYSE",
            f"{base}.NASDAQ"
        ]

    return symbols

# ------------------- Smart Symbol Resolution -------------------
def resolve_symbol(user_input: str):
    prompt = build_groq_prompt_for_symbol(user_input)
    groq_res = call_groq_ai_symbol(prompt)
    if "symbol" in groq_res:
        return groq_res["symbol"]
    else:
        logging.warning(f"Groq could not resolve symbol, using input as fallback: {user_input}")
        return user_input

# ------------------- Price Fetch with Fallback -------------------
def fetch_price_with_fallback(symbols):
    for sym in symbols:
        price_data = get_price(sym)
        if price_data:
            return price_data

        # Fallback: Yahoo Finance
        try:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={sym}"
            resp = requests.get(url, timeout=5).json()
            quote = resp.get("quoteResponse", {}).get("result", [])
            if quote:
                q = quote[0]
                return {
                    "symbol": q.get("symbol"),
                    "price": q.get("regularMarketPrice"),
                    "low": q.get("regularMarketDayLow"),
                    "high": q.get("regularMarketDayHigh"),
                    "volume": q.get("regularMarketVolume"),
                    "avg_volume": q.get("averageDailyVolume3Month"),
                    "change_percent": q.get("regularMarketChangePercent")
                }
        except Exception as e:
            logging.warning(f"Yahoo fallback failed for {sym}: {e}")

        # Fallback: Alpha Vantage
        if alpha_key:
            try:
                alpha_url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={sym}&apikey={alpha_key}"
                resp = requests.get(alpha_url, timeout=5).json()
                data = resp.get("Global Quote", {})
                if data:
                    return {
                        "symbol": data.get("01. symbol"),
                        "price": float(data.get("05. price", 0)),
                        "low": float(data.get("04. low", 0)),
                        "high": float(data.get("03. high", 0)),
                        "volume": int(data.get("06. volume", 0)),
                        "avg_volume": None,
                        "change_percent": float(data.get("10. change percent", "0%").replace("%", "")),
                    }
            except Exception as e:
                logging.warning(f"Alpha Vantage fallback failed for {sym}: {e}")

    return None

# ------------------- Core Engine -------------------
def run_engine(user_input, entry_price=None):
    try:
        resolved_symbol = resolve_symbol(user_input)
        logging.info(f"Resolved symbol: {resolved_symbol}")

        symbols = normalize_symbol(resolved_symbol)
        logging.info(f"Normalized symbols: {symbols}")

        price_data = fetch_price_with_fallback(symbols)
        if not price_data:
            logging.warning(f"No price data found for any symbol in {symbols}")
            return {
                "symbol": symbols,
                "error": "No price data found",
                "alerts": ["error"]
            }

        price = price_data["price"]
        low = price_data["low"]
        high = price_data["high"]
        volume = price_data["volume"]
        avg_volume = price_data.get("avg_volume")
        change_percent = price_data["change_percent"]

        alerts = []
        if entry_price:
            if price > entry_price * 1.05:
                alerts.append("profit")
            elif price < entry_price * 0.95:
                alerts.append("loss")

        sentiment_score, s_type = sentiment_for_symbol(price_data["symbol"])
        if s_type == "accumulation":
            alerts.append("buy_signal")
        elif s_type == "hype":
            alerts.append("trap_warning")

        suggested_entry = None
        if low and high:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

        chart_base64 = generate_chart(price_data["symbol"])

        prompt = build_groq_prompt(price_data["symbol"], price_data, sentiment_score)
        ai_analysis = call_groq_ai(prompt)

        return {
            "symbol": price_data["symbol"],
            "price": price,
            "low": low,
            "high": high,
            "volume": volume,
            "avg_volume": avg_volume,
            "change_percent": change_percent,
            "sentiment": sentiment_score,
            "sentiment_type": s_type,
            "alerts": alerts,
            "suggested_entry": suggested_entry,
            "chart": chart_base64,
            "ai_analysis": ai_analysis
        }

    except Exception as e:
        logging.error(f"Engine failed: {str(e)}")
        return {
            "symbol": user_input,
            "error": str(e),
            "alerts": ["error"]
        }

# ------------------- Entry Point -------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--entry", type=float)
    args = parser.parse_args()

    result = run_engine(args.symbol, args.entry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
