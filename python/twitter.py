import os
import time
import requests
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk import download

# Download VADER lexicon if not present
try:
    download('vader_lexicon')
except:
    pass

# ----------------- Sentiment Analyzer -----------------
sentiment_cache = {}
sia = SentimentIntensityAnalyzer()

# ----------------- Tweets Cache -----------------
tweets_cache = {}  # {symbol: {"timestamp": ..., "tweets": [...] }}
CACHE_TTL = 300  # 5 minutes

# ----------------- Fetch Tweets -----------------
def fetch_tweets(symbol: str, max_results: int = 50) -> list:
    now = time.time()

    # Return cached tweets if valid
    if symbol in tweets_cache:
        if now - tweets_cache[symbol]["timestamp"] < CACHE_TTL:
            return tweets_cache[symbol]["tweets"]

    url = "https://api.twitter.com/2/tweets/search/recent"
    token = os.getenv("X_BEARER_TOKEN")

    if not token:
        print("⚠️ Twitter token missing. Returning empty tweets.")
        tweets_cache[symbol] = {"timestamp": now, "tweets": []}
        return []

    headers = {"Authorization": f"Bearer {token}"}
    query = f"({symbol} OR #{symbol}) (bullish OR bearish OR buy OR sell OR breakout OR crash OR dump OR moon) lang:en -is:retweet"
    params = {
        "query": query,
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)

        # Handle rate limit
        if response.status_code == 429:
            print(f"Rate limit hit for {symbol}, using cache.")

            # Get cached tweets if any
            cached_tweets = tweets_cache.get(symbol, {}).get("tweets", [])

            # Build full consistent response
            result = {
                "symbol": symbol,
                "tweets_count": len(cached_tweets),
                "alerts": [],  # always include
                "sentiment_label": "Neutral",
                "sentiment_score": 0.0,
                "bullish_ratio": 0.5,
                "rate_limited": True
            }
            return result

        # Any other error
        if response.status_code != 200:
            print(f"Twitter API error {response.status_code} for {symbol}")
            # Get cached tweets if any
            cached_tweets = tweets_cache.get(symbol, {}).get("tweets", [])

            # Build full consistent response
            result = {
                "symbol": symbol,
                "tweets": cached_tweets,
                "alerts": [],
                "sentiment_label": "Neutral",
                "sentiment_score": 0,
                "bullish_ratio": 0.5,
                "rate_limited": True,
                "chart": None,  # or cached chart if you have
                "price_data": {}  # optional, to match expected structure
            }
            return result

        try:
            raw = response.json()
            data = raw.get("data", [])
        except Exception:
            print("Twitter JSON parse failed.")
            # Get cached tweets if any
            cached_tweets = tweets_cache.get(symbol, {}).get("tweets", [])

            # Build full consistent response
            result = {
                "symbol": symbol,
                "tweets": cached_tweets,
                "alerts": [],
                "sentiment_label": "Neutral",
                "sentiment_score": 0,
                "bullish_ratio": 0.5,
                "rate_limited": True,
                "chart": None,  # or cached chart if you have
                "price_data": {}  # optional, to match expected structure
            }
            return result

        tweets = [
            {
                "text": t.get("text", ""),
                "likes": t.get("public_metrics", {}).get("like_count", 0),
                "retweets": t.get("public_metrics", {}).get("retweet_count", 0)
            }
            for t in data
        ]

        tweets_cache[symbol] = {"timestamp": now, "tweets": tweets}
        return tweets

    except Exception as e:
        print(f"Twitter fetch failed for {symbol}: {e}")
        cached_tweets = tweets_cache.get(symbol, {}).get("tweets", [])

            # Build full consistent response
        result = {
            "symbol": symbol,
            "tweets": cached_tweets,
            "alerts": [],
            "sentiment_label": "Neutral",
            "sentiment_score": 0,
            "bullish_ratio": 0.5,
            "rate_limited": True,
            "chart": None,  # or cached chart if you have
            "price_data": {}  # optional, to match expected structure
        }
        return result


# ----------------- Sentiment Analysis -----------------
def analyze_sentiment(text: str) -> tuple:
    key = text[:200]
    if key in sentiment_cache:
        return sentiment_cache[key]

    try:
        scores = sia.polarity_scores(text)
        compound = scores['compound']
    except:
        return ("neutral", 0.0)

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    sentiment_cache[key] = (label, abs(compound))
    return sentiment_cache[key]


def aggregate_sentiment(tweets: list) -> dict:
    try:
        pos = neg = neu = 0.0

        for t in tweets:
            label, _ = analyze_sentiment(t.get("text", ""))
            weight = 1 + (t.get("likes", 0) * 0.1) + (t.get("retweets", 0) * 0.2)

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

        return {
            "bias": bias,
            "confidence": confidence,
            "bullish_ratio": round(bullish_ratio, 2)
        }

    except Exception as e:
        print("Aggregate sentiment failed:", e)
        return {"bias": "neutral", "confidence": 0.0, "bullish_ratio": 0.5}
