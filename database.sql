CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone VARCHAR UNIQUE,
  plan VARCHAR DEFAULT 'free',
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE watchlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  symbol VARCHAR
);

CREATE TABLE portfolio (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  symbol VARCHAR,
  entry_price NUMERIC,
  quantity INT
);

CREATE TABLE alerts_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID,
  symbol VARCHAR,
  alert_type VARCHAR,
  sent_at TIMESTAMP DEFAULT now()
);

CREATE TABLE twitter_sentiment (
  symbol VARCHAR,
  score INT,
  type VARCHAR,
  created_at TIMESTAMP DEFAULT now()
);