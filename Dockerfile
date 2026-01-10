# =========================
# Base image with Python
# =========================
FROM python:3.11-slim

# Force rebuild when needed
ARG CACHEBUST=2025-01-01

# =========================
# Install Node.js
# =========================
RUN apt-get update && apt-get install -y curl build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

# =========================
# Install Node dependencies
# =========================
WORKDIR /app/node

# Copy ONLY package files first (for Docker cache)
COPY node/package*.json ./

RUN npm install --omit=dev

# Copy rest of Node app (includes public/)
COPY node/ ./

# =========================
# Install Python dependencies
# =========================
WORKDIR /app

# Copy FULL python folder
COPY python/ ./python/

RUN pip install --no-cache-dir -r python/requirements.txt

# =========================
# Runtime config
# =========================
ENV PORT=3000
EXPOSE 3000

# 🔥 VERY IMPORTANT FIX
WORKDIR /app/node

# =========================
# Start Node app
# =========================
CMD ["node", "index.js"]
