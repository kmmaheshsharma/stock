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
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk import download

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

# ------------------- NLTK Setup -------------------
download('vader_lexicon')
sia = SentimentIntensityAnalyzer()
sentiment_cache = {}

# ------------------- Symbol Utilities -------------------
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
        return [raw]

    base = match.group(0)
    return [
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

def extract_candidate_symbol(text):
    if not text:
        return None
    text = text.lower()
    stopwords = [
        "get","show","me","price","for","of","the","stock","crypto","coin","token",
        "please","tell","give","fetch","display","what","is","my","buy","sell","track",
        "add","to","entry","exit","purchase","rate","value","worth","current","today",
        "analysis","report","analyze","information","info","on","at","a","and","in","with",
        "as","by","that","this","it","its","i","you","we","they","he","she","him","her",
        "them","our","your","their","us","my","mine","yours","theirs","ours","invest",
        "investment","market","markets","share","shares","equity","equities","fund","funds",
        "portfolio","portfolios","index","indices","etf","etfs","mutual","mutuals","bond",
        "bonds","derivative","derivatives","option","options","future","futures","currency",
        "currencies","forex","digital","digitals","asset","assets","blockchain","blockchains",
        "decentralized","decentralizeds","finance","finances","technology","technologies",
        "company","companies","corporation","corporations","limited","ltd","inc","incorporated",
        "plc","llc","group","groups","international","nationwide","global","solutions","systems",
        "technologies","holdings","services","service","industries","industry","enterprises",
        "enterprise","ventures","venture","partners","partner"
    ]
    words = re.findall(r"[a-zA-Z0-9&]+", text)
    filtered = [w for w in words if w not in stopwords]
    if not filtered:
        return None
    return max(filtered, key=len).upper()

def search_yahoo_symbol(name):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={name}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200:
            return None
        quotes = r.json().get("quotes", [])
        if not quotes:
            return None
        name_upper = name.upper()
        for q in quotes:
            if name_upper in q.get("symbol","").upper():
                return q["symbol"]
        for q in quotes:
            if name_upper in q.get("shortname","").upper():
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

# ------------------- Twitter Sentiment -------------------
def fetch_tweets(symbol):
    token = os.getenv('X_BEARER_TOKEN')
    if not token:
        logging.warning("Twitter Bearer token not set")
        return []
    query = f"({symbol} OR #{symbol}) (bullish OR bearish OR buy OR sell OR breakout OR crash OR dump OR moon) lang:en -is:retweet"
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"query": query,"max_results":50,"tweet.fields":"created_at,public_metrics"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json().get("data", [])
        return [{"text": t["text"],"likes": t["public_metrics"]["like_count"],"retweets": t["public_metrics"]["retweet_count"]} for t in data]
    except Exception as e:
        logging.warning(f"Twitter error: {e}")
        return []

def analyze_sentiment(text):
    key = text[:200]
    if key in sentiment_cache:
        return sentiment_cache[key]
    scores = sia.polarity_scores(text)
    compound = scores['compound']
    if compound >= 0.05:
        label="positive"
    elif compound <= -0.05:
        label="negative"
    else:
        label="neutral"
    sentiment_cache[key]=(label, abs(compound))
    return sentiment_cache[key]

def aggregate_sentiment(tweets):
    pos=neg=neu=0.0
    for t in tweets:
        label, score = analyze_sentiment(t["text"])
        weight = 1 + (t["likes"]*0.1) + (t["retweets"]*0.2)
        if label=="positive":
            pos+=weight
        elif label=="negative":
            neg+=weight
        else:
            neu+=weight
    directional = pos+neg
    if directional==0:
        return {"bias":"neutral","confidence":0.0,"bullish_ratio":0.5}
    bullish_ratio = pos/directional
    if bullish_ratio>0.65:
        bias="bullish"
    elif bullish_ratio<0.35:
        bias="bearish"
    else:
        bias="neutral"
    confidence = round(abs(bullish_ratio-0.5)*2,2)
    return {"bias":bias,"confidence":confidence,"bullish_ratio":round(bullish_ratio,2)}

# ------------------- Core Engine -------------------
def run_engine(symbol, entry_price=None):
    try:
        candidate = extract_candidate_symbol(symbol)
        if not candidate:
            return {"symbol":symbol,"error":"Could not extract symbol","alerts":["error"]}

        yahoo_symbol = search_yahoo_symbol(candidate)
        logging.info(f"Yahoo resolved symbol: {yahoo_symbol} for candidate: {candidate}")

        symbols = normalize_symbol(yahoo_symbol if yahoo_symbol else candidate)
        logging.info(f"Normalized symbols: {symbols}")

        price_data = None
        resolved_symbol = None
        for sym in symbols:
            price_data = get_price(sym)
            if price_data:
                resolved_symbol = sym
                break

        if not price_data:
            logging.warning(f"No price data for any of symbols: {symbols}")
            return {"symbol":symbols[0],"error":"No price data found","alerts":["error"]}

        result = sentiment_for_symbol(resolved_symbol)

        price = price_data.get("price")
        low = price_data.get("low")
        high = price_data.get("high")
        volume = price_data.get("volume")
        avg_volume = price_data.get("avg_volume")
        change_percent = price_data.get("change_percent")

        alerts = []
        if entry_price:
            if price>entry_price*1.05: alerts.append("profit")
            elif price<entry_price*0.95: alerts.append("loss")

        s_type = result["sentiment_label"]
        if s_type=="Bullish" or s_type=="accumulation": alerts.append("buy_signal")
        elif s_type=="Hype": alerts.append("trap_warning")
        elif s_type=="Bearish" or s_type=="distribution": alerts.append("sell_signal")

        suggested_entry = None
        if low and high:
            suggested_entry={"lower":round(low*0.99,2),"upper":round(low*1.02,2)}

        chart_base64 = generate_chart(resolved_symbol)

        prompt = build_groq_prompt(resolved_symbol, price_data, result["sentiment_score"], result["sentiment_label"], result["confidence"], result["explanation"])
        ai_analysis = call_groq_ai(prompt)

        return {
            "symbol": resolved_symbol,
            "price": price,
            "low": low,
            "high": high,
            "volume": volume,
            "avg_volume": avg_volume,
            "change_percent": change_percent,
            "sentiment_score": result["sentiment_score"],
            "sentiment_label": result["sentiment_label"],
            "confidence": result["confidence"],
            "emoji": result["emoji"],
            "explanation": result["explanation"],
            "alerts": alerts,
            "suggested_entry": suggested_entry,
            "chart": chart_base64,
            "ai_analysis": ai_analysis
        }

    except Exception as e:
        logging.error(f"Engine failed: {str(e)}")
        return {"symbol":symbol,"error":str(e),"alerts":["error"]}

# ------------------- Entry Point -------------------
if __name__=="__main__":
    logging.info("Engine started via command line.")
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--entry", type=float)
    args = parser.parse_args()

    result = run_engine(args.symbol,args.entry)
    print(json.dumps(result,ensure_ascii=False,indent=2))
