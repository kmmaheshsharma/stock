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
if not api_key:
    logging.warning("GROQ_API_KEY not found in environment variables.")
groq_client = Groq(api_key=api_key)

def build_groq_prompt_for_symbol(message):
    return f"""
    You are a professional market analyst.

    A user has asked for the analysis of a stock or cryptocurrency.
    The name or symbol given by the user is:
    '{message}'

    Please provide the full, correct trading symbol.
    Examples:
    - Stocks: AAPL, SBIN.NS, TSLA
    - Crypto: BTC-USD, ETH-USD

    Only return the symbol.
    """

def call_groq_ai_symbol(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
    logging.info("Starting Groq AI call...")
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

        symbol = raw_text.strip()

        if re.match(r'^[A-Z0-9\-]{1,15}(\.[A-Z]{2,10})?$', symbol):
            logging.info(f"Extracted symbol: {symbol}")
            return {"symbol": symbol}
        else:
            logging.warning(f"Invalid symbol format in response: {symbol}")
            return {"error": "Invalid symbol format", "raw_text": raw_text}

    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e)}

def call_groq_ai(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
    logging.info("Starting Groq AI call...")
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
    raw = raw.replace("-", " ").replace("_", " ")

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

    # ------------------- CRYPTO ADDITIONS (NEW) -------------------
    crypto_variants = [
        f"{base}-USD",
        f"{base}-USDT",
        f"{base}-BTC"
    ]

    symbols.extend(crypto_variants)

    return symbols
import re

def extract_candidate_symbol(text):
    if not text:
        return None

    text = str(text)

    cleaned = re.sub(r"\b(get|show|me|price|for|of|the|stock|crypto|please|fetch|give)\b", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z0-9& ]", " ", cleaned)

    words = cleaned.strip().split()
    if not words:
        return None

    # pick longest meaningful word
    candidate = max(words, key=len)

    if not candidate:
        return None

    return candidate.upper()

def search_yahoo_symbol(name):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={name}"
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, timeout=5)

        if r.status_code != 200:
            return None

        data = r.json()
        quotes = data.get("quotes", [])
        logging.info(f"Yahoo search found {len(quotes)} quotes for '{name}'")
        if not quotes:
            return None

        # Prefer EQUITY
        equities = [q for q in quotes if q.get("quoteType") == "EQUITY"]
        logging.info(f"Found {len(equities)} EQUITY quotes for '{name}'")
        if equities:
            # Prefer NSE
            for q in equities:
                if q["symbol"].endswith(".NS"):
                    return q["symbol"]

            return equities[0]["symbol"]

        # fallback
        return quotes[0]["symbol"]

    except Exception as e:
        logging.error(f"Yahoo search error: {e}")
        return None

# ------------------- Core Engine -------------------
def run_engine(symbol, entry_price=None):
    try:
        candidate = extract_candidate_symbol(symbol)
        logging.info(f"Extracted candidate symbol: {candidate}")
        if not candidate:
            return None       
        yahoo_symbol = search_yahoo_symbol(candidate)
        logging.info(f"Yahoo Finance search result: {yahoo_symbol}")    
        symbols = normalize_symbol(yahoo_symbol)
        logging.info(f"Normalized symbols: {yahoo_symbol}")

        price_data = None
        for sym in symbols:
            price_data = get_price(sym)
            if price_data:
                break

        if not price_data:
            logging.warning("No price data found.")
            return {
                "symbol": symbols,
                "error": "No price data found",
                "alerts": ["error"]
            }

        price = price_data["price"]
        low = price_data["low"]
        high = price_data["high"]
        volume = price_data["volume"]
        avg_volume = price_data["avg_volume"]
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
            "symbol": symbol,
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
