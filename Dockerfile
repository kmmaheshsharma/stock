# Cache bust: blank line
# Force rebuild: cache bust comment
FROM python:3.11-slim

# Install python explicitly
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs build-essential

WORKDIR /app

COPY node/package*.json ./node/
COPY python/requirements.txt ./python/
ARG CACHEBUST=20251228_3
RUN npm install --omit=dev
COPY . .
# Debug: print pip version before install
RUN pip --version
# Install Python dependencies after all files are copied
RUN pip install -r python/requirements.txt
# Debug: print pip version after install
RUN pip --version

ENV PORT=3000
EXPOSE 3000

CMD ["node", "node/index.js"]