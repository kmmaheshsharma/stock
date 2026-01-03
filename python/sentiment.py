from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from twitter import fetch_tweets

analyzer = SentimentIntensityAnalyzer()


def base_symbol(symbol: str) -> str:
    """
    Convert KPIGREEN.NS -> KPIGREEN
    Safe even if .NS is not present
    """
    return symbol.replace(".NS", "").upper()


def sentiment_for_symbol(symbol):
    """
    symbol is expected as KPIGREEN.NS
    """
    clean_symbol = base_symbol(symbol)

    tweets = fetch_tweets(clean_symbol)
    if not tweets:
        return 0, "neutral"

    # Calculate compound scores
    scores = [analyzer.polarity_scores(t)["compound"] for t in tweets]
    avg = sum(scores) / len(scores)

    score = round(avg * 100)

    # Hype detection
    hype_count = sum(("🚀" in t or "🔥" in t) for t in tweets)
    if hype_count > 3:
        return score, "hype"

    # Sentiment buckets
    if avg > 0.05:
        return score, "accumulation"
    if avg < -0.05:
        return score, "distribution"

    return score, "neutral"
