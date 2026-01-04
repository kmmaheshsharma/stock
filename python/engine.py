import sys
import json
import argparse
import re
import os
from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart

# ------------------- Groq AI -------------------
from groq import Groq

# Initialize Groq client (make sure GROQ_API_KEY is set in your environment)
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def call_groq_ai(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
    """
    Calls Groq AI and parses JSON output.
    """
    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a professional stock market analyst."},
                {"role": "user", "content": prompt}
            ],
            model=model,
            max_tokens=max_tokens,
            temperature=0.3
        )

        raw_text = response.choices[0].message.content

        # Try to parse JSON from AI
        ai_json = json.loads(raw_text)
        return ai_json

    except json.JSONDecodeError:
        # fallback if AI returns invalid JSON
        return {"error": "Invalid JSON from Groq AI", "raw_text": raw_text}

    except Exception as e:
        return {"error": str(e)}

def build_groq_prompt(symbol, price_data, sentiment_score):
    """
    Builds a stock context prompt for Groq AI with structured JSON request
    """
    return f"""
You are a professional stock market analyst.

Analyze the following stock data:

Symbol: {symbol}
Current Price: {price_data['price']}
Daily Low: {price_data['low']}
Daily High: {price_data['high']}
Volume: {price_data['volume']}
Average Volume: {price_data['avg_volume']}
Change %: {price_data['change_percent']}
Sentiment Score: {sentiment_score}

Return a JSON object with the following keys:
- predicted_move (up/down/neutral)
- confidence (0.0-1.0)
- support_level
- resistance_level
- risk (low/medium/high)
- recommendation (short comment)

Only return valid JSON.
"""

# ------------------- Symbol Normalization -------------------
def normalize_symbol(raw: str):
    """
    Extract ONLY the base stock symbol from user input
    Supports NSE & BSE
    """
    raw = raw.upper().strip()
    raw = re.sub(r"\b(TRACK|ENTRY|BUY|SELL|ADD|SHOW|PRICE)\b", "", raw)
    raw = raw.replace("-", " ").replace("_", " ")
    match = re.search(r"\b[A-Z&]{2,15}\b", raw)
    if not match:
        raise ValueError(f"Invalid symbol received: {raw}")
    base = match.group(0)
    return [f"{base}.NS", f"{base}.BO"]

# ------------------- Core Engine -------------------
def run_engine(symbol, entry_price=None):
    try:
        symbols = normalize_symbol(symbol)
        price_data = get_price(symbols)

        if not price_data:
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

        # ------------------- Groq AI Integration -------------------
        prompt = build_groq_prompt(price_data["symbol"], price_data, sentiment_score)
        ai_analysis = call_groq_ai(prompt)

        # ------------------- Return Combined JSON -------------------
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
