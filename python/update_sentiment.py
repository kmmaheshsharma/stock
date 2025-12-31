
import os
from dotenv import load_dotenv
dotenv_path = os.path.abspath("../node/.env")  # adjust if needed
load_dotenv(dotenv_path)
import psycopg2
from sentiment import sentiment_for_symbol

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("symbol", type=str)
args = parser.parse_args()

symbol = args.symbol
score, sentiment_type = sentiment_for_symbol(symbol)

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    dbname=os.getenv("PG_DATABASE"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    sslmode="require" if os.getenv("PG_SSL") == "true" else "disable"
)
cur = conn.cursor()
try:
    cur.execute("""
    INSERT INTO twitter_sentiment (symbol, score, type)
    VALUES (%s, %s, %s)
    ON CONFLICT (symbol)
    DO UPDATE SET score=EXCLUDED.score, type=EXCLUDED.type, created_at=now()
    """, (symbol, score, sentiment_type))
    conn.commit()
except Exception as e:
    print(f"[PG ERROR] Failed to log {symbol}: {e}")

cur.close()
conn.close()
print(f"Updated twitter_sentiment for {symbol}: {score}, {sentiment_type}")