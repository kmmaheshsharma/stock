import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from sentiment import sentiment_for_symbol  # Updated function
import argparse

# -------- ARG PARSING --------
parser = argparse.ArgumentParser()
parser.add_argument("symbol", type=str)
args = parser.parse_args()
symbol = args.symbol

# -------- FETCH SENTIMENT --------
result = sentiment_for_symbol(symbol)

# Unpack values
score = result["sentiment_score"]
sentiment_label = result["sentiment_label"]
confidence = result["confidence"]
emoji = result["emoji"]
explanation = result["explanation"]

# -------- POSTGRES CONNECTION --------
conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    dbname=os.getenv("PG_DATABASE"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    sslmode="require" if os.getenv("PG_SSL") == "true" else "disable"
)
cur = conn.cursor()

# -------- UPSERT DATA --------
try:
    cur.execute("""
        INSERT INTO twitter_sentiment (symbol, score, type, confidence, emoji, explanation)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol)
        DO UPDATE SET
            score = EXCLUDED.score,
            type = EXCLUDED.type,
            confidence = EXCLUDED.confidence,
            emoji = EXCLUDED.emoji,
            explanation = EXCLUDED.explanation,
            created_at = now()
    """, (symbol.upper(), score, sentiment_label, confidence, emoji, explanation))
    conn.commit()
except Exception as e:
    print(f"[PG ERROR] Failed to log {symbol}: {e}")

cur.close()
conn.close()

# -------- DISPLAY --------
print(f"Updated twitter_sentiment for {symbol.upper()}:")
print(f"Score: {score}")
print(f"Type: {sentiment_label} {emoji}")
print(f"Confidence: {confidence}")
print(f"Explanation: {explanation}")
