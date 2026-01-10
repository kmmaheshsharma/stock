import os
import requests
from transformers import pipeline
sentiment_cache = {}
finbert = pipeline(
    "sentiment-analysis",
    model="ProsusAI/finbert",
    tokenizer="ProsusAI/finbert"
)
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

    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        print("Twitter error:", r.text)
        return []

    return [
        {
            "text": t["text"],
            "likes": t["public_metrics"]["like_count"],
            "retweets": t["public_metrics"]["retweet_count"]
        }
        for t in r.json().get("data", [])
    ]

def analyze_sentiment(text):
    key = text[:200]

    if key in sentiment_cache:
        return sentiment_cache[key]

    result = finbert(text[:512])[0]
    sentiment_cache[key] = (result["label"], result["score"])
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
        return {
            "bias": "neutral",
            "confidence": 0.0,
            "bullish_ratio": 0.5
        }

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
