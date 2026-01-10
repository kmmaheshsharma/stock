import os
import requests
import time
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk import download

# Download VADER lexicon if not present
download('vader_lexicon')

# ----------------- Sentiment Analyzer -----------------
sentiment_cache = {}
sia = SentimentIntensityAnalyzer()

# ----------------- Tweets Cache -----------------
tweets_cache = {}  # {symbol: {"timestamp": ..., "tweets": [...] }}
CACHE_TTL = 300  # cache for 5 minutes

def fetch_tweets(symbol, max_results=50):
    """
    Fetch recent tweets for a symbol, with caching and rate-limit handling.
    Returns [] immediately if token is missing.
    """
    token = os.getenv('X_BEARER_TOKEN')
    if not token:
        print("X_BEARER_TOKEN missing! Skipping Twitter fetch.")
        return []

    now = time.time()

    # Return cached tweets if within TTL
    if symbol in tweets_cache:
        cache_entry = tweets_cache[symbol]
        if now - cache_entry["timestamp"] < CACHE_TTL:
            return cache_entry["tweets"]

    query = (
        f"({symbol} OR #{symbol}) "
        "(bullish OR bearish OR buy OR sell OR breakout OR crash OR dump OR moon) "
        "lang:en -is:retweet"
    )

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "query": query,
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics"
    }

    retries = 3
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)

            if r.status_code == 429:
                wait_time = 10 * (attempt + 1)  # reduce wait for testing
                print(f"Rate limit hit for {symbol}, sleeping {wait_time}s...")
                time.sleep(wait_time)
                continue

            r.raise_for_status()
            data = r.json().get("data", [])

            tweets = [
                {
                    "text": t["text"],
                    "likes": t["public_metrics"]["like_count"],
                    "retweets": t["public_metrics"]["retweet_count"]
                }
                for t in data
            ]

            # Cache results
            tweets_cache[symbol] = {"timestamp": now, "tweets": tweets}
            return tweets

        except requests.exceptions.RequestException as e:
            print(f"Error fetching tweets for {symbol}: {e}")
            time.sleep(2)  # reduce sleep for faster retries

    print(f"Failed to fetch tweets for {symbol} after {retries} attempts.")
    return []

# ----------------- Sentiment Analysis -----------------
def analyze_sentiment(text):
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

def aggregate_sentiment(tweets):
    pos = neg = neu = 0.0

    for t in tweets:
        label, score = analyze_sentiment(t["text"])
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
