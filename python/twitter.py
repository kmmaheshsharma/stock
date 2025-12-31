import os
import requests

def fetch_tweets(symbol):
    query = f"{symbol} stock OR {symbol} share OR #{symbol}"
    url = "https://api.twitter.com/2/tweets/search/recent"

    headers = {
        "Authorization": f"Bearer {os.getenv('X_BEARER_TOKEN')}"
    }

    params = {
        "query": query,
        "max_results": 50,
        "tweet.fields": "created_at"
    }

    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        return []

    return [t["text"] for t in r.json().get("data", [])]