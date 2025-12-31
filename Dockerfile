# ---- Base: Python 3.11 (guaranteed compatible with yfinance) ----
FROM python:3.11-slim

# ---- Install Node.js 22 ----
RUN apt-get update && apt-get install -y curl \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y nodejs \
  && node --version \
  && python --version

# ---- App directory ----
WORKDIR /app

# ---- Node dependencies ----
COPY node/package*.json ./node/
RUN cd node && npm install --omit=dev

# ---- Python dependencies ----
COPY python/requirements.txt ./python/
RUN pip install --upgrade pip \
  && pip install -r python/requirements.txt

# ---- App source ----
COPY . .

ENV PORT=3000
EXPOSE 3000

CMD ["node", "node/index.js"]
