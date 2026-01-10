import os
import time
import requests
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk import download

# Download VADER lexicon if not present
download('vader_lexicon')

# ----------------- Sentiment Analyzer -----------------
sentiment_cache = {}
sia = SentimentIntensityAnalyzer()

# ----------------- Tweets Cache -----------------
# Caches tweets per symbol (even empty lists)
tweets_cache = {}  # {symbol: {"timestamp": ..., "tweets": [...] }}
CACHE_TTL = 300  # cache for 5 minutes

# ----------------- Fetch Tweets -----------------
def fetch_tweets(symbol: str, max_results: int = 50, retries: int = 1, backoff: int = 2) -> list:
    now = time.time()

    # Return cached tweets if within TTL
    if symbol in tweets_cache and now - tweets_cache[symbol]["timestamp"] < CACHE_TTL:
        return tweets_cache[symbol]["tweets"]

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {os.getenv('X_BEARER_TOKEN')}"}
    query = f"({symbol} OR #{symbol}) (bullish OR bearish OR buy OR sell OR breakout OR crash OR dump OR moon) lang:en -is:retweet"
    params = {"query": query, "max_results": max_results, "tweet.fields": "created_at,public_metrics"}

    for attempt in range(retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)

            # Handle rate limit
            if response.status_code == 429:
                print(f"Rate limit hit for {symbol}, retrying in {backoff} sec (attempt {attempt+1}/{retries+1})...")
                time.sleep(backoff)
                backoff *= 2
                continue

            # Handle other non-200 responses
            if response.status_code != 200:
                print(f"Non-200 response for {symbol}: {response.status_code}, skipping attempt")
                continue

            # Parse JSON safely
            try:
                data = response.json().get("data", [])
            except ValueError:
                print(f"JSON parse error for {symbol}, skipping attempt")
                continue

            tweets = [
                {
                    "text": t.get("text", ""),
                    "likes": t.get("public_metrics", {}).get("like_count", 0),
                    "retweets": t.get("public_metrics", {}).get("retweet_count", 0)
                } for t in data
            ]

            # Save to cache and return
            tweets_cache[symbol] = {"timestamp": now, "tweets": tweets}
            return tweets

        except requests.exceptions.RequestException as e:
            print(f"Network/API error for {symbol}: {e}")

    # Fallback to cached data if API fails or rate limited
    if symbol in tweets_cache:
        print(f"Returning cached data for {symbol} due to API failure or rate limit")
        return tweets_cache[symbol]["tweets"]

    # Return empty if nothing is available
    print(f"No data available for {symbol}, returning empty list")
    tweets_cache[symbol] = {"timestamp": now, "tweets": []}
    return []

# ----------------- Sentiment Analysis -----------------
def analyze_sentiment(text: str) -> tuple:
    key = text[:200]
    if key in sentiment_cache:
        return sentiment_cache[key]

    scores = sia.polarity_scores(text)
    compound = scores['compound']

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    sentiment_cache[key] = (label, abs(compound))
    return sentiment_cache[key]

def aggregate_sentiment(tweets: list) -> dict:
    pos = neg = neu = 0.0
    for t in tweets:
        label, _ = analyze_sentiment(t["text"])
        weight = 1 + (t["likes"] * 0.1) + (t["retweets"] * 0.2)
        if label == "positive":
            pos += weight
        elif label == "negative":
            neg += weight
        else:
            neu += weight

    directional = pos + neg
    if directional == 0:
        return {"bias": "neutral", "confidence": 0.0, "bullish_ratio": 0.5}

    bullish_ratio = pos / directional
    if bullish_ratio > 0.65:
        bias = "bullish"
    elif bullish_ratio < 0.35:
        bias = "bearish"
    else:
        bias = "neutral"

    confidence = round(abs(bullish_ratio - 0.5) * 2, 2)
    return {"bias": bias, "confidence": confidence, "bullish_ratio": round(bullish_ratio, 2)}

# ----------------- Symbol Helper -----------------
import re
def base_symbol(symbol: str) -> str:
    return re.sub(r"\.\w+$", "", symbol).upper()

# ----------------- Display-ready Sentiment -----------------
def sentiment_for_symbol(symbol: str) -> dict:
    clean_symbol = base_symbol(symbol)
    tweets = fetch_tweets(symbol) or []

    if not tweets:
        return {
            "symbol": clean_symbol,
            "sentiment_score": 0,
            "sentiment_label": "Neutral",
            "confidence": 0.0,
            "emoji": "⚪",
            "explanation": "No sufficient Twitter data",
            "tweets_count": 0
        }

    sentiment = aggregate_sentiment(tweets)
    bias = sentiment.get("bias", "neutral")
    confidence = sentiment.get("confidence", 0.0)
    bullish_ratio = sentiment.get("bullish_ratio", 0.5)
    score = int(bullish_ratio * 100 * confidence)

    mapping = {
        "bullish": ("Bullish", "📈", "Twitter crowd is bullish on this stock"),
        "bearish": ("Bearish", "📉", "Twitter crowd is bearish on this stock"),
        "neutral": ("Neutral", "⚪", "Twitter sentiment is mixed or unclear")
    }
    label, emoji, explanation = mapping.get(bias, mapping["neutral"])

    return {
        "symbol": clean_symbol,
        "sentiment_score": score,
        "sentiment_label": label,
        "confidence": confidence,
        "emoji": emoji,
        "explanation": explanation,
        "tweets_count": len(tweets)
    }

# ----------------- Hype Detection -----------------
def detect_hype(tweets: list, sentiment: dict) -> bool:
    if not tweets or not sentiment:
        return False

    hype_words = ["moon", "rocket", "breakout", "pump", "爆", "🚀", "🔥"]
    hype_score = sum(
        sum(1 for w in hype_words if w in t["text"].lower())
        for t in tweets
    )
    weighted_hype = hype_score * sentiment.get("confidence", 0.0)
    return weighted_hype >= 3

# ----------------- Example -----------------
if __name__ == "__main__":
    symbol = "KPIGREEN.NS"
    sentiment = sentiment_for_symbol(symbol)
    print("Sentiment:", sentiment)

    tweets = fetch_tweets(symbol)
    hype = detect_hype(tweets, sentiment)
    print("Hype detected:", hype)
