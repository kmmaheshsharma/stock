FROM python:3.11-slim

ARG CACHEBUST=2025-01-01

# =========================
# System deps + Node.js
# =========================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# =========================
# Node deps
# =========================
WORKDIR /app/node
COPY node/package*.json ./
RUN npm install --omit=dev && npm cache clean --force
COPY node/ ./

# =========================
# Python deps
# =========================
WORKDIR /app
COPY python/requirements.txt ./python/requirements.txt

RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r python/requirements.txt && \
    rm -rf /root/.cache/pip

COPY python/ ./python/

# =========================
# Runtime
# =========================
ENV PORT=3000
EXPOSE 3000

WORKDIR /app/node
CMD ["node", "index.js"]
