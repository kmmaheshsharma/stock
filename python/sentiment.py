import re
from twitter import fetch_tweets, aggregate_sentiment

def base_symbol(symbol: str) -> str:
    """
    Convert Yahoo/other formatted symbols to base symbol.
    E.g., KPIGREEN.NS -> KPIGREEN
    """
    try:
        return re.sub(r"\.\w+$", "", symbol).upper()
    except:
        return symbol.upper()


def sentiment_for_symbol(symbol: str) -> dict:
    """
    Returns display-ready sentiment data.
    Always returns a safe object.
    Never raises exceptions.
    """
    try:
        clean_symbol = base_symbol(symbol)

        # Fetch tweets safely
        tweets = fetch_tweets(symbol) or []

        # No tweets → neutral fallback
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

        # Weighted score (0–100)
        try:
            score = int(bullish_ratio * 100 * confidence)
        except:
            score = 0

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

    except Exception as e:
        print(f"Sentiment failed for {symbol}: {e}")

        # Hard fallback — never break engine
        return {
            "symbol": symbol.upper(),
            "sentiment_score": 0,
            "sentiment_label": "Neutral",
            "confidence": 0.0,
            "emoji": "⚪",
            "explanation": "Sentiment service unavailable",
            "tweets_count": 0
        }


def detect_hype(tweets: list, sentiment: dict) -> bool:
    """
    Detect hype safely.
    Never throws.
    """
    try:
        if not tweets or not sentiment:
            return False

        hype_words = ["moon", "rocket", "breakout", "pump", "爆", "🚀", "🔥"]

        hype_score = sum(
            sum(1 for w in hype_words if w in t.get("text", "").lower())
            for t in tweets
        )

        weighted_hype = hype_score * sentiment.get("confidence", 0.0)

        return weighted_hype >= 3

    except:
        return False
