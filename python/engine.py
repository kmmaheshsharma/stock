import sys
import json
import argparse
import re
import os
import logging
from market import get_price
from sentiment import sentiment_for_symbol
from chart import generate_chart

# ------------------- Logging Setup -------------------
logging.basicConfig(
    level=logging.INFO,  # INFO and above will be printed
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ------------------- Groq AI -------------------
from groq import Groq

# Initialize Groq client (make sure GROQ_API_KEY is set in your environment)
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    logging.warning("GROQ_API_KEY not found in environment variables.")
groq_client = Groq(api_key=api_key)
def sanitize_input(message):
    """
    Removes unwanted characters or extra parameters from the user input
    to ensure only the company name is passed.
    """
    # Remove unwanted segments (like `,--entry,1600`)
    cleaned_message = re.sub(r'(,--entry,\d+)', '', message)  # Remove any --entry parameters

    # Optionally, remove non-alphanumeric characters or spaces
    cleaned_message = cleaned_message.strip()

    # Log cleaned message for debugging
    logging.debug(f"Sanitized input message: {cleaned_message}")

    return cleaned_message
def build_groq_prompt_for_symbol(message):
    """
    Builds a prompt to ask Groq AI to extract and correct the stock symbol from the input message.
    """
    return f"""
    You are a professional stock market analyst.

    A user has asked for the analysis of a company. The company name given by the user is:
    '{message}'

    Please provide the full, correct stock symbol (like 'ABC', 'XYZ.NS', or 'XYZ.BO') that matches this company.
    Only return the stock symbol, not additional information.
    """

def call_groq_ai_symbol(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
    """
    Calls Groq AI and extracts the stock symbol.
    """
    logging.info(f"Starting Groq AI call for symbol extraction...{prompt}")
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
        logging.info("Groq AI response received.")

        # Log the full raw response for debugging
        logging.debug(f"Full raw response from Groq AI: {raw_text}")

        # Clean the response to ensure it only contains the symbol
        symbol = raw_text.strip()

        # Handle the case where the symbol is empty
        if not symbol:
            logging.error("Empty symbol received from Groq AI.")
            return {"error": "Empty symbol returned", "raw_text": raw_text}

        # Check if the symbol matches expected format (e.g., ABC, XYZ.NS)
        if re.match(r'^[A-Z]{1,5}(\.[A-Z]{2,3})?$', symbol.replace(" ", "").replace("\n", "")):  # Remove spaces/newlines
            logging.info(f"Extracted symbol: {symbol}")
            return symbol
        else:
            logging.warning(f"Invalid symbol format in response: {symbol}")
            return {"error": "Invalid symbol format", "raw_text": raw_text}

    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e), "raw_text": raw_text}

def call_groq_ai(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
    """
    Calls Groq AI and extracts JSON safely.
    """
    logging.info("Starting Groq AI call...")
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
        logging.info("Groq AI response received.")

        # Try to extract JSON object from response
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            ai_json = json.loads(match.group(0))
            logging.info("Groq AI JSON parsed successfully.")
            return ai_json

        logging.warning("No JSON found in Groq AI response, returning raw text.")
        return {"error": "Invalid JSON from Groq AI", "raw_text": raw_text}

    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e), "raw_text": raw_text}

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
        logging.info(f"Normalized symbols: {symbols}")
        
        # Assuming get_price can take a list of symbols, else use symbols[0] or fix accordingly
        price_data = get_price(symbols[0])  

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
    sanitized_message = sanitize_input(args.symbol)
    prompt = build_groq_prompt_for_symbol(sanitized_message)
    ai_response = call_groq_ai_symbol(prompt)
    
    # Fix the symbol extraction and error checking
    if ai_response.get("error"):
        logging.error(f"Error in symbol extraction: {ai_response['error']}")
        sys.exit(1)

    symbol = ai_response.get("symbol", "").strip()

    if not symbol:
        logging.error("No valid stock symbol found in the message.")
        sys.exit(1)

    logging.info(f"Extracted stock symbol: {symbol}")    
    result = run_engine(symbol, args.entry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
