from twitter import fetch_tweets, aggregate_sentiment

def base_symbol(symbol: str) -> str:
    """
    Convert KPIGREEN.NS -> KPIGREEN
    Safe even if .NS is not present
    """
    return symbol.replace(".NS", "").upper()

def sentiment_for_symbol(symbol: str) -> dict:
    """
    Returns DISPLAY-READY sentiment data using lightweight VADER analysis
    """
    clean_symbol = base_symbol(symbol)
    tweets = fetch_tweets(symbol)

    if not tweets:
        return {
            "symbol": clean_symbol,
            "sentiment_score": 0,
            "sentiment_label": "Neutral",
            "confidence": 0.0,
            "emoji": "⚪",
            "explanation": "No sufficient Twitter data"
        }

    sentiment = aggregate_sentiment(tweets)

    bias = sentiment.get("bias", "neutral")
    confidence = sentiment.get("confidence", 0.0)
    bullish_ratio = sentiment.get("bullish_ratio", 0.5)

    # Convert bullish_ratio to a 0–100 score
    score = int(bullish_ratio * 100)

    # Map bias to label, emoji, explanation
    if bias == "bullish":
        label = "Bullish"
        emoji = "📈"
        explanation = "Twitter crowd is bullish on this stock"
    elif bias == "bearish":
        label = "Bearish"
        emoji = "📉"
        explanation = "Twitter crowd is bearish on this stock"
    else:
        label = "Neutral"
        emoji = "⚪"
        explanation = "Twitter sentiment is mixed or unclear"

    return {
        "symbol": clean_symbol,
        "sentiment_score": score,
        "sentiment_label": label,
        "confidence": confidence,
        "emoji": emoji,
        "explanation": explanation
    }

def detect_hype(tweets, sentiment):
    """
    Detect social media hype based on common hype words and confidence
    """
    if not tweets or not sentiment:
        return False

    hype_words = ["moon", "rocket", "breakout", "pump", "爆", "🚀", "🔥"]

    hype_count = sum(
        any(word in t["text"].lower() for word in hype_words)
        for t in tweets
    )

    return hype_count >= 5 and sentiment.get("confidence", 0.0) > 0.7
