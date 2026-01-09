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

# ------------------- COMMON FILLER WORDS -------------------
COMMON_FILLER = {
    "the","my","please","show","me","get","give","analysis","for","of","stock","crypto","analyze",
    "price","today","current","latest","check","tell","about","on","is","a","an","and",
    "in","with","to","from","that","this","can","i","you","us","now","kindly","kind",
    "information","details","would","like","want","send","do","does","did","how","what",
    "latest","recent","update","updates","quote","quotes","market","markets","ticker","tickers",
    "help","any","some","please","show","me","here","there","where","when","why","which",
    "buy","sell","hold","entry","exit","track","tracking","portfolio","portfolios","investment",
    "investments","fund","funds","share","shares","unit","units","price","prices","value","values","worth","worths"
}

# ------------------- Smart Symbol Extraction -------------------
def extract_possible_name(sentence: str):
    """
    Extract the most likely stock/crypto name from any random sentence.
    """
    sentence = sentence.lower().strip()
    sentence = re.sub(r'[^\w\s&\-.]', ' ', sentence)  # keep &, -, .
    words = sentence.split()

    # Remove filler words
    candidates = [w for w in words if w not in COMMON_FILLER]

    if not candidates:
        return sentence  # fallback: use full input

    # Scoring: longer words, words with letters, numbers, hyphens are preferred
    def score_word(word):
        score = len(word)
        if re.search(r'[0-9]', word):
            score += 2
        if '-' in word or '&' in word or '.' in word:
            score += 2
        return score

    candidates.sort(key=score_word, reverse=True)
    best_candidate = candidates[0]

    logging.info(f"Extracted possible symbol word from sentence: '{best_candidate}'")
    return best_candidate

# ------------------- Symbol Resolver -------------------
def resolve_symbol_from_name(name: str):
    """
    Resolve partial company/crypto name to exact trading symbol.
    Tries Yahoo Finance first (all results), then Groq AI fallback.
    """
    name_clean = name.strip().upper()
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={name_clean}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if "quotes" in data and len(data["quotes"]) > 0:
                # Try to find a quote whose symbol or shortname matches the input closely
                for quote in data["quotes"]:
                    symbol = quote.get("symbol")
                    shortname = quote.get("shortname", "").upper()
                    if symbol and (name_clean in symbol.upper() or name_clean in shortname):
                        logging.info(f"Yahoo search resolved '{name}' → '{symbol}'")
                        return symbol
                # fallback to first quote if no close match
                symbol = data["quotes"][0]["symbol"]
                logging.info(f"Yahoo search fallback '{name}' → '{symbol}'")
                return symbol
    except Exception as e:
        logging.warning(f"Yahoo search failed for '{name}': {e}")

    # Fallback: Groq AI
    prompt = f"""
    You are a professional market analyst.
    A user typed the name: '{name}'.
    Provide the exact trading symbol (stock or crypto). Only return the symbol.
    """
    result = call_groq_ai_symbol(prompt)
    if "symbol" in result:
        logging.info(f"Groq AI resolved '{name}' → '{result['symbol']}'")
        return result["symbol"]

    logging.error(f"Could not resolve symbol for '{name}'")
    return None


# ------------------- Groq AI Helpers -------------------
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

    # ------------------- CRYPTO ADDITIONS -------------------
    crypto_variants = [
        f"{base}-USD",
        f"{base}-USDT",
        f"{base}-BTC"
    ]

    symbols.extend(crypto_variants)

    return symbols

# ------------------- Core Engine -------------------
def run_engine(user_input, entry_price=None):
    try:
        # 1️⃣ Extract likely symbol word from user input
        candidate_word = extract_possible_name(user_input)

        # 2️⃣ Resolve the exact symbol
        resolved_symbol = resolve_symbol_from_name(candidate_word)
        if not resolved_symbol:
            raise ValueError(f"Could not resolve symbol for '{candidate_word}'")

        symbols = normalize_symbol(resolved_symbol)
        logging.info(f"Normalized symbols: {symbols}")

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
