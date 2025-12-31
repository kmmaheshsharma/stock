FROM python:3.11-slim

ARG CACHEBUST=2025-12-31-01

RUN apt-get update && apt-get install -y curl build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

WORKDIR /app/node

COPY node/package*.json ./
RUN npm install --omit=dev

COPY node/ ./

ENV PORT=3000
EXPOSE 3000

CMD ["node", "index.js"]
