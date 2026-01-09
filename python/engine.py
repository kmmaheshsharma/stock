import sys
import json
import argparse
import re
import os
import logging
import requests
from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart
from groq import Groq

# ------------------- Logging Setup -------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ------------------- Groq AI -------------------
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
    "help","any","some","here","there","where","when","why","which",
    "buy","sell","hold","entry","exit","track","tracking","portfolio","portfolios","investment",
    "investments","fund","funds","share","shares","unit","units","value","values","worth","worths"
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
        # fallback: use longest word in sentence
        words.sort(key=len, reverse=True)
        candidates = words

    # Scoring: longer words, letters+numbers/hyphen preferred
    def score_word(word):
        score = len(word)
        if re.search(r'[0-9]', word):
            score += 2
        if '-' in word or '&' in word or '.' in word:
            score += 2
        return score

    candidates.sort(key=score_word, reverse=True)
    best_candidate = candidates[0]

    logging.info(f"Extracted possible symbol word: '{best_candidate}'")
    return best_candidate.upper()

# ------------------- Yahoo Symbol Resolver -------------------
def yahoo_symbol_lookup(name: str):
    """
    Query Yahoo Finance to get the correct symbol.
    """
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={name}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if "quotes" in data and len(data["quotes"]) > 0:
                symbol = data["quotes"][0]["symbol"]
                logging.info(f"Yahoo resolved '{name}' → '{symbol}'")
                return symbol
    except Exception as e:
        logging.warning(f"Yahoo lookup failed for '{name}': {e}")
    return None

# ------------------- Groq AI Single Call -------------------
def call_groq_analysis(user_input: str):
    """
    Send the full user message to Groq and get symbol + analysis in one shot.
    """
    prompt = f"""
You are a professional financial analyst.

A user has asked for the stock/crypto information using the following text:
'{user_input}'

1️⃣ Extract the exact trading symbol (stock or crypto) if possible.
2️⃣ Get the current price, daily high, daily low, volume, change %.
3️⃣ Give a short analysis and recommendation.

Return a JSON object like this:
{{
  "symbol": "RELIANCE.NS",
  "price": 1234.56,
  "low": 1200.12,
  "high": 1250.00,
  "volume": 1234567,
  "avg_volume": 1100000,
  "change_percent": 1.23,
  "sentiment_score": 0.5,
  "recommendation": "Buy / Hold / Sell",
  "notes": "Any short AI analysis"
}}
Only return valid JSON. Do not include any extra text.
"""

    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a professional market analyst."},
                {"role": "user", "content": prompt}
            ],
            model="openai/gpt-oss-20b",
            max_tokens=600,
            temperature=0.3
        )

        raw_text = response.choices[0].message.content
        logging.info("Groq AI response received.")

        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            ai_json = json.loads(match.group(0))
            return ai_json

        logging.warning("No JSON found in Groq AI response.")
        return {"error": "Invalid JSON from Groq AI", "raw_text": raw_text}
    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e)}

# ------------------- Core Engine -------------------
def run_engine(user_input, entry_price=None):
    try:
        # 1️⃣ Extract candidate word
        candidate_word = extract_possible_name(user_input)

        # 2️⃣ Try Yahoo Finance first
        resolved_symbol = yahoo_symbol_lookup(candidate_word)

        # 3️⃣ Call Groq only once, fallback if Yahoo fails
        ai_data = call_groq_analysis(user_input)

        # If Yahoo found a symbol, replace Groq symbol for price lookup
        if resolved_symbol:
            ai_data["symbol"] = resolved_symbol

        # ------------------- Price & Sentiment -------------------
        price_data = get_price(ai_data["symbol"]) or {}
        price = price_data.get("price", ai_data.get("price"))
        low = price_data.get("low", ai_data.get("low"))
        high = price_data.get("high", ai_data.get("high"))
        volume = price_data.get("volume", ai_data.get("volume"))
        avg_volume = price_data.get("avg_volume", ai_data.get("avg_volume"))
        change_percent = price_data.get("change_percent", ai_data.get("change_percent"))

        # Alerts
        alerts = []
        if entry_price:
            if price and price > entry_price * 1.05:
                alerts.append("profit")
            elif price and price < entry_price * 0.95:
                alerts.append("loss")

        # Sentiment
        sentiment_score, s_type = sentiment_for_symbol(ai_data.get("symbol"))
        if s_type == "accumulation":
            alerts.append("buy_signal")
        elif s_type == "hype":
            alerts.append("trap_warning")

        suggested_entry = None
        if low and high:
            suggested_entry = {"lower": round(low*0.99,2), "upper": round(low*1.02,2)}

        chart_base64 = generate_chart(ai_data.get("symbol"))

        return {
            "symbol": ai_data.get("symbol"),
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
            "ai_analysis": ai_data
        }

    except Exception as e:
        logging.error(f"Engine failed: {str(e)}")
        return {"symbol": user_input, "error": str(e), "alerts": ["error"]}

# ------------------- Entry Point -------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--entry", type=float)
    args = parser.parse_args()

    result = run_engine(args.symbol, args.entry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
