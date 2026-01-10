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

# ------------------- Prompt Builders -------------------
def build_groq_prompt(symbol, price_data, sentiment_score, sentiment_score_label, confidence, explanation):
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
Sentiment Label: {sentiment_score_label}
Confidence: {confidence}
Explanation: {explanation}

Return a JSON object with the following keys:
- predicted_move
- confidence
- support_level
- resistance_level
- risk
- recommendation

Only return valid JSON.
"""

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

# ------------------- Groq AI Call Wrappers -------------------
def call_groq_ai_symbol(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
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
        symbol = raw_text.strip()

        if re.match(r'^[A-Z0-9\-]{1,15}(\.[A-Z]{2,10})?$', symbol):
            return {"symbol": symbol}
        else:
            return {"error": "Invalid symbol format", "raw_text": raw_text}

    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e)}

def call_groq_ai(prompt: str, model="openai/gpt-oss-20b", max_tokens=400):
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
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            try:
                ai_json = json.loads(match.group(0))
                return ai_json
            except Exception as e_json:
                logging.warning(f"Groq AI returned invalid JSON: {e_json}")
                return {"error": "Invalid JSON from Groq AI", "raw_text": raw_text}

        logging.warning("No JSON found in Groq AI response, returning raw text.")
        return {"error": "Invalid JSON from Groq AI", "raw_text": raw_text}

    except Exception as e:
        logging.error(f"Groq AI call failed: {str(e)}")
        return {"error": str(e)}

# ------------------- Symbol Normalization -------------------
def normalize_symbol(raw: str):
    raw = raw.upper().strip()
    raw = re.sub(r"\b(TRACK|ENTRY|BUY|SELL|ADD|SHOW|PRICE)\b", "", raw)
    raw = raw.replace("_", " ").strip()

    known_suffixes = [".NS", ".BO", ".US", ".NYSE", ".NASDAQ", "-USD", "-USDT", "-BTC"]

    for suf in known_suffixes:
        if raw.endswith(suf):
            return [raw]

    match = re.search(r"\b[A-Z0-9&]{1,20}\b", raw)
    if not match:
        raise ValueError(f"Invalid symbol received: {raw}")

    base = match.group(0)
    symbols = [
        f"{base}.NS",
        f"{base}.BO",
        base,
        f"{base}.US",
        f"{base}.NYSE",
        f"{base}.NASDAQ",
        f"{base}-USD",
        f"{base}-USDT",
        f"{base}-BTC"
    ]
    return symbols

def extract_candidate_symbol(text):
    if not text:
        return None

    text = text.lower()

    stopwords = [
        "get", "show", "me", "price", "for", "of", "the",
        "stock", "crypto", "coin", "token", "please",
        "tell", "give", "fetch", "display", "what", "is", "my",
        "buy", "sell", "track", "add", "to", "entry",
        "exit", "purchase", "rate", "value", "worth", "current", 
        "today", "analysis", "report", "analyze", "information", "info",
        "on", "at", "a", "and", "in", "of", "with", "as", "by", "that", "this", "it", "its", "i", "you", "we", "they", "he", "she",
        "him", "her", "them", "our", "your", "their", "us", "my", "mine", "yours", "theirs", "ours",
        "invest", "investment", "market", "markets", "share", "shares", "equity", "equities",
        "fund", "funds", "portfolio", "portfolios", "index", "indices", "etf", "etfs",
        "mutual", "mutuals", "bond", "bonds", "derivative", "derivatives",
        "option", "options", "future", "futures", "currency", "currencies", "forex", "forexes",
        "digital", "digitals", "asset", "assets", "blockchain", "blockchains", "decentralized", "decentralizeds",
        "finance", "finances", "technology", "technologies", "company", "companies", "corporation", "corporations",
        "limited", "ltd", "inc", "incorporated", "plc", "llc", "group", "groups", "international", "nationwide", "global", "solutions", "systems",
        "technologies", "holdings", "services", "service", "industries", "industry", "enterprises", "enterprise", "ventures", "venture", "partners", "partner"
    ]

    words = re.findall(r"[a-zA-Z0-9&]+", text)
    filtered = [w for w in words if w not in stopwords]

    if not filtered:
        return None

    candidate = max(filtered, key=len)
    return candidate.upper()

def search_yahoo_symbol(name):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={name}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)

        if r.status_code != 200:
            return None

        data = r.json()
        quotes = data.get("quotes", [])
        if not quotes:
            return None

        name_upper = name.upper()
        for q in quotes:
            symbol = q.get("symbol", "")
            if name_upper in symbol.upper():
                return symbol

        for q in quotes:
            shortname = q.get("shortname", "")
            if name_upper in shortname.upper():
                return q["symbol"]

        equities = [q for q in quotes if q.get("quoteType") == "EQUITY"]
        if equities:
            for q in equities:
                if q["symbol"].endswith(".NS"):
                    return q["symbol"]
            return equities[0]["symbol"]

        return quotes[0]["symbol"]

    except Exception as e:
        logging.error(f"Yahoo search error: {e}")
        return None

# ------------------- Core Engine -------------------
def run_engine(symbol, entry_price=None):
    try:
        candidate = extract_candidate_symbol(symbol)
        if not candidate:
            return {"symbol": symbol, "error": "Could not extract candidate symbol", "alerts": ["error"]}

        yahoo_symbol = search_yahoo_symbol(candidate)
        logging.info(f"Yahoo resolved symbol: {yahoo_symbol} for candidate: {candidate}")

        if yahoo_symbol:
            symbols = normalize_symbol(yahoo_symbol)
            logging.info(f"Normalized symbols from Yahoo: {symbols}")
        else:
            logging.warning(f"Yahoo could not resolve symbol: {candidate}. Trying raw normalization.")
            symbols = normalize_symbol(candidate)

        price_data = None
        resolved_symbol = None
        for sym in symbols:
            price_data = get_price(sym)
            resolved_symbol = sym
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

        # ----------------- Sentiment -----------------
        try:
            result = sentiment_for_symbol(resolved_symbol)
        except Exception as e:
            logging.warning(f"Sentiment analysis failed: {e}")
            result = {
                "symbol": resolved_symbol,
                "sentiment_score": 0,
                "sentiment_label": "Neutral",
                "confidence": 0.0,
                "emoji": "⚪",
                "explanation": "Sentiment service unavailable"
            }
        print(f"Sentiment result for {resolved_symbol}: {result}")
        s_type = result.get("sentiment_label", "Neutral")
        if s_type == "Bullish" or s_type == "accumulation":
            alerts.append("buy_signal")
        elif s_type == "Hype":
            alerts.append("trap_warning")
        elif s_type == "Bearish" or s_type == "distribution":
            alerts.append("sell_signal")

        suggested_entry = None
        if low and high:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

        chart_base64 = generate_chart(resolved_symbol)

        try:
            prompt = build_groq_prompt(
                resolved_symbol, price_data, result["sentiment_score"],
                result["sentiment_label"], result["confidence"], result["explanation"]
            )
            ai_analysis = call_groq_ai(prompt)
        except Exception as e_ai:
            logging.warning(f"Groq AI analysis failed: {e_ai}")
            ai_analysis = {"error": "Groq AI call failed"}
        print(f"mahesh Groq AI analysis for {resolved_symbol}: {ai_analysis}")
        return {
            "symbol": resolved_symbol,
            "price": price,
            "low": low,
            "high": high,
            "volume": volume,
            "avg_volume": avg_volume,
            "change_percent": change_percent,
            "sentiment_score": result.get("sentiment_score", 0),
            "sentiment_label": result.get("sentiment_label", "Neutral"),
            "confidence": result.get("confidence", 0.0),
            "emoji": result.get("emoji", "⚪"),
            "explanation": result.get("explanation", ""),
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
    logging.info("Engine started via command line.")
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--entry", type=float)
    args = parser.parse_args()

    result = run_engine(args.symbol, args.entry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
