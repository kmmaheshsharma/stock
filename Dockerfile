FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs build-essential

WORKDIR /app

# Copy Node files and install
COPY node/package*.json ./node/
RUN cd node && npm install --omit=dev

# Copy Python requirements and install
COPY python/requirements.txt ./python/
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -r ./python/requirements.txt

# Copy rest of project
COPY .env .env
COPY . .

CMD ["node", "node/alerts.js"]
