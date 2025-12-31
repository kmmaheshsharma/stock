FROM python:3.11-slim

# Install Node.js
RUN apt-get update && apt-get install -y curl build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

# 👇 IMPORTANT
WORKDIR /app/node

# Copy Node files
COPY node/package*.json ./
RUN npm install --omit=dev

# Copy rest of Node app
COPY node/ ./

# (Optional) Python
WORKDIR /app
COPY python/requirements.txt ./python/
RUN pip install -r python/requirements.txt

ENV PORT=3000
EXPOSE 3000

CMD ["node", "node/index.js"]
