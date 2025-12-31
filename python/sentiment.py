from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from twitter import fetch_tweets

analyzer = SentimentIntensityAnalyzer()

def sentiment_for_symbol(symbol):
    tweets = fetch_tweets(symbol)
    if not tweets:
        return 0, "neutral"

    # Calculate compound scores for all tweets
    scores = [analyzer.polarity_scores(t)["compound"] for t in tweets]
    avg = sum(scores) / len(scores)

    # Convert to percentage if you like
    score = round(avg * 100)

    # Check for hype first
    hype_count = sum("🚀" in t or "🔥" in t for t in tweets)
    if hype_count > 3:
        return score, "hype"

    # Adjust thresholds to match typical VADER scores
    if avg > 0.05:      # small positive sentiment
        return score, "accumulation"
    if avg < -0.05:     # small negative sentiment
        return score, "distribution"

    # Otherwise neutral
    return score, "neutral"
