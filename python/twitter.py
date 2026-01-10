import os
import requests
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk import download

# Download VADER lexicon if not present
download('vader_lexicon')

sentiment_cache = {}
sia = SentimentIntensityAnalyzer()

def fetch_tweets(symbol):
    query = (
        f"({symbol} OR #{symbol}) "
        "(bullish OR bearish OR buy OR sell OR breakout OR crash OR dump OR moon) "
        "lang:en -is:retweet"
    )

    url = "https://api.twitter.com/2/tweets/search/recent"

    headers = {
        "Authorization": f"Bearer {os.getenv('X_BEARER_TOKEN')}"
    }

    params = {
        "query": query,
        "max_results": 50,
        "tweet.fields": "created_at,public_metrics"
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        r.raise_for_status()
    except Exception as e:
        print("Twitter error:", e)
        return []

    data = r.json().get("data", [])
    return [
        {
            "text": t["text"],
            "likes": t["public_metrics"]["like_count"],
            "retweets": t["public_metrics"]["retweet_count"]
        }
        for t in data
    ]

def analyze_sentiment(text):
    key = text[:200]
    if key in sentiment_cache:
        return sentiment_cache[key]

    scores = sia.polarity_scores(text)
    compound = scores['compound']

    # Map to simplified positive/negative/neutral
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
