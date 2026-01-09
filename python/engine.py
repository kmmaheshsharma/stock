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

# ------------------- Groq AI Helpers -------------------
def call_groq_ai(prompt: str, model="openai/gpt-oss-20b", max_tokens=600):
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

        # Extract JSON from response
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

# ------------------- Core Engine (Single Groq call) -------------------
def run_engine(user_input, entry_price=None):
    try:
        # 1️⃣ Extract likely symbol word from user input
        candidate_word = extract_possible_name(user_input)

        # 2️⃣ Build Groq prompt for symbol + full analysis
        prompt = f"""
You are a professional financial analyst.

A user asked for analysis. The input message is:
'{user_input}'

- Identify the correct trading symbol (stock or crypto) from this input.
- Get the latest price, daily low/high, volume, avg volume, change percent.
- Determine Twitter/market sentiment score (numeric).
- Return a JSON object with these keys:
  - symbol
  - price
  - low
  - high
  - volume
  - avg_volume
  - change_percent
  - sentiment_score
  - predicted_move
  - confidence
  - support_level
  - resistance_level
  - risk
  - recommendation
  - alerts (optional)

Only return valid JSON.
"""

        groq_response = call_groq_ai(prompt)
        if "error" in groq_response:
            raise ValueError(f"Groq AI failed: {groq_response.get('error')}")

        # 3️⃣ Extract resolved symbol
        resolved_symbol = groq_response.get("symbol")
        if not resolved_symbol:
            raise ValueError("Groq AI did not return a symbol.")

        # 4️⃣ Normalize symbol variants & get price
        symbols = normalize_symbol(resolved_symbol)
        logging.info(f"Normalized symbols: {symbols}")

        price_data = None
        for sym in symbols:
            price_data = get_price(sym)
            if price_data:
                break

        if not price_data:
            logging.warning("No price data found from market API. Using Groq values.")
            price_data = {
                "symbol": resolved_symbol,
                "price": groq_response.get("price"),
                "low": groq_response.get("low"),
                "high": groq_response.get("high"),
                "volume": groq_response.get("volume"),
                "avg_volume": groq_response.get("avg_volume"),
                "change_percent": groq_response.get("change_percent")
            }
            alerts = groq_response.get("alerts", ["error"])
        else:
            alerts = []

        # 5️⃣ Entry alerts
        price = price_data.get("price")
        low = price_data.get("low")
        high = price_data.get("high")
        volume = price_data.get("volume")
        avg_volume = price_data.get("avg_volume")
        change_percent = price_data.get("change_percent")

        if entry_price and price:
            if price > entry_price * 1.05:
                alerts.append("profit")
            elif price < entry_price * 0.95:
                alerts.append("loss")

        # 6️⃣ Sentiment
        sentiment_score = groq_response.get("sentiment_score")
        if sentiment_score is None:
            sentiment_score, s_type = sentiment_for_symbol(price_data["symbol"])
        else:
            s_type = "accumulation" if sentiment_score > 0 else "hype"

        if s_type == "accumulation":
            alerts.append("buy_signal")
        elif s_type == "hype":
            alerts.append("trap_warning")

        # 7️⃣ Suggested entry levels
        suggested_entry = None
        if low and high:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

        # 8️⃣ Chart
        chart_base64 = generate_chart(price_data["symbol"])

        # 9️⃣ AI analysis fields
        ai_analysis_keys = ["predicted_move","confidence","support_level","resistance_level","risk","recommendation"]
        ai_analysis = {k: groq_response.get(k) for k in ai_analysis_keys}

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
