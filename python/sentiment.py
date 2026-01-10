import re
from twitter import fetch_tweets, aggregate_sentiment

def base_symbol(symbol: str) -> str:
    """
    Convert Yahoo/other formatted symbols to base symbol.
    E.g., KPIGREEN.NS -> KPIGREEN, safe for any exchange suffix.
    """
    return re.sub(r"\.\w+$", "", symbol).upper()

def sentiment_for_symbol(symbol: str) -> dict:
    """
    Returns display-ready sentiment data using lightweight VADER analysis.
    Handles missing tweets and weights score by confidence.
    Caches empty results to avoid repeated API calls when no tweets exist.
    """
    clean_symbol = base_symbol(symbol)
    
    # Fetch tweets (caching inside fetch_tweets handles empty lists too)
    tweets = fetch_tweets(symbol) or []

    # No tweets found: return neutral
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

    # Aggregate sentiment
    sentiment = aggregate_sentiment(tweets)
    bias = sentiment.get("bias", "neutral")
    confidence = sentiment.get("confidence", 0.0)
    bullish_ratio = sentiment.get("bullish_ratio", 0.5)

    # Weighted score (0-100)
    score = int(bullish_ratio * 100 * confidence)

    # Map bias to label, emoji, explanation
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

def detect_hype(tweets: list, sentiment: dict) -> bool:
    """
    Detect social media hype based on common hype words and confidence.
    Works even with empty tweets list.
    """
    if not tweets or not sentiment:
        return False

    hype_words = ["moon", "rocket", "breakout", "pump", "爆", "🚀", "🔥"]

    # Count total hype word occurrences across tweets
    hype_score = sum(
        sum(1 for w in hype_words if w in t["text"].lower())
        for t in tweets
    )

    # Weighted by sentiment confidence
    weighted_hype = hype_score * sentiment.get("confidence", 0.0)

    # Threshold: trigger hype if weighted score >= 3
    return weighted_hype >= 3

# -----------------------------
# Example usage
# -----------------------------
if __name__ == "__main__":
    symbol = "KPIGREEN.NS"

    sentiment = sentiment_for_symbol(symbol)
    print("Sentiment:", sentiment)

    tweets = fetch_tweets(symbol) or []
    hype = detect_hype(tweets, sentiment)
    print("Hype detected:", hype)
