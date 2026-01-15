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
import pandas as pd
import yfinance as yf
from indicators import get_indicators_for_symbol
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
logging.getLogger("matplotlib").setLevel(logging.ERROR)
logging.getLogger("PIL").setLevel(logging.ERROR)
# ------------------- Logging Setup -------------------
class StderrHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__(sys.stderr)

logging.getLogger().handlers = []
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[StderrHandler()]
)

# ------------------- Groq AI -------------------
from groq import Groq

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    logging.warning("GROQ_API_KEY not found in environment variables.")
groq_client = Groq(api_key=api_key)

# ------------------- Prompt Builders -------------------
def build_groq_prompt(symbol, price_data, sentiment_score):
    return f"""
You are a professional financial analyst.

Analyze the following asset (stock or crypto):

Symbol: "{symbol}"
Current Price: {price_data.get('price', 0.0)}
Daily Low: {price_data.get('low', 0.0)}
Daily High: {price_data.get('high', 0.0)}
Volume: {price_data.get('volume', 0)}
Average Volume: {price_data.get('avg_volume', 0)}
Change %: {price_data.get('change_percent', 0.0)}
Sentiment Score: {sentiment_score}

Return a JSON object ONLY with the following keys (no extra text):
- predicted_move (values: "up", "down", "neutral")
- confidence (float between 0 and 1)
- support_level (float)
- resistance_level (float)
- risk (values: "low", "moderate", "high")
- recommendation (values: "buy", "sell", "hold")

Do not include any explanations or extra text. Output must be valid JSON.
"""

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


def build_groq_combined_prompt(symbol, price_data, sentiment_score, indicators):
    return f"""
You are a professional financial and technical market analyst.

Analyze the following asset using BOTH market data and technical indicators.

Symbol: "{symbol}"

Market Data:
- Current Price: {price_data.get('price', 0.0)}
- Daily Low: {price_data.get('low', 0.0)}
- Daily High: {price_data.get('high', 0.0)}
- Volume: {price_data.get('volume', 0)}
- Average Volume: {price_data.get('avg_volume', 0)}
- Change %: {price_data.get('change_percent', 0.0)}
- Sentiment Score: {sentiment_score}

Technical Indicators:
- EMA20: {indicators['ema20']}
- EMA50: {indicators['ema50']}
- RSI: {indicators['rsi']}
- MACD Value: {indicators['macd']['value']}
- MACD Signal: {indicators['macd']['signal']}
- MACD Histogram: {indicators['macd']['histogram']}

Return ONLY valid JSON with NO extra text:

{{
  "predicted_move": "up | down | neutral",
  "technical_analysis": {{
    "ema_alignment": "bullish | bearish | neutral",
    "rsi_state": "overbought | oversold | neutral",
    "macd_state": "bullish | bearish | neutral",
    "technical_bias": "bullish | bearish | neutral",
    "reason": "short explanation"
  }},
  "confidence_hint": {{
    "technical": 0-100,
    "sentiment": 0-100
  }},
  "levels": {{
    "support": float,
    "resistance": float
  }},
  "trade_plan": {{
    "entry": float,
    "stop_loss": float,
    "targets": [float, float, float]
  }},
  "risk": "low | moderate | high",
  "recommendation": "buy | sell | hold"
}}

IMPORTANT RULES:
- Do NOT calculate final confidence
- confidence_hint is only an estimation
- No explanations outside JSON
"""


# ------------------- Core Engine -------------------
def run_engine(symbol, entry_price=None):
    try:
        def safe_float(x):
            try:
                return float(x)
            except:
                return None

        def safe_int(x):
            try:
                return int(x)
            except:
                return None

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

        price = safe_float(price_data.get("price"))
        low = safe_float(price_data.get("low"))
        high = safe_float(price_data.get("high"))
        volume = safe_int(price_data.get("volume"))
        avg_volume = safe_int(price_data.get("avg_volume"))
        change_percent = safe_float(price_data.get("change_percent"))

        alerts = []
        # ----------------- Technical Indicators -----------------
        #indicators = get_technical_indicators(resolved_symbol)

        technical_analysis = {}
        technical_score = 0
        
        indicators = get_indicators_for_symbol(resolved_symbol)
        if not indicators:
            indicators = {
                "ema20": None,
                "ema50": None,
                "rsi": None,
                "macd": {"value": None, "signal": None, "histogram": None}
            }
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

        s_type = result.get("sentiment_label", "Neutral")
        if s_type == "Bullish" or s_type == "accumulation":
            alerts.append("buy_signal")
        elif s_type == "Hype":
            alerts.append("trap_warning")
        elif s_type == "Bearish" or s_type == "distribution":
            alerts.append("sell_signal")

        suggested_entry = None
        if low is not None and high is not None:
            suggested_entry = {
                "lower": round(low * 0.99, 2),
                "upper": round(low * 1.02, 2)
            }

        chart_base64 = generate_chart(resolved_symbol)

        try:
            prompt = build_groq_combined_prompt(
                resolved_symbol, price_data, result.get("sentiment_score", 0, ), indicators
            )
            ai_analysis = call_groq_ai(prompt)
            if not isinstance(ai_analysis, dict):
                ai_analysis = {"error": "Invalid AI response"}            
        except Exception as e_ai:
            logging.warning(f"Groq AI analysis failed: {e_ai}")
            ai_analysis = {"error": "Groq AI call failed"}

        confidence_breakdown = {
            "technical": technical_score,
            "sentiment": int(result.get("confidence", 0) * 100),
            "volume": 60 if volume and avg_volume and volume > avg_volume else 45,
            "price_action": 60,  # can improve later
            "trend": 65 if technical_score > 60 else 50
        }

        overall_confidence = round(
            confidence_breakdown["technical"] * 0.30 +
            confidence_breakdown["volume"] * 0.20 +
            confidence_breakdown["sentiment"] * 0.15 +
            confidence_breakdown["price_action"] * 0.20 +
            confidence_breakdown["trend"] * 0.15
        )


        return {
            "symbol": resolved_symbol,
            "price": price,
            "low": low,
            "high": high,
            "volume": volume,
            "avg_volume": avg_volume,
            "change_percent": change_percent,

            "sentiment_score": safe_float(result.get("sentiment_score", 0)),
            "sentiment_label": result.get("sentiment_label", "Neutral"),

            "confidence": overall_confidence,
            "confidence_breakdown": confidence_breakdown,

            "technical_indicators": indicators,
            "technical_analysis": technical_analysis,

            "emoji": result.get("emoji", "⚪"),
            "explanation": technical_analysis.get("reason", ""),
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
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
   
