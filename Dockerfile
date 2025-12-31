FROM node:22-bullseye

# Install Python
RUN apt-get update \
  && apt-get install -y python3 python3-pip \
  && ln -sf /usr/bin/python3 /usr/bin/python \
  && python3 --version

# App root
WORKDIR /app

# Copy Node package files FIRST
COPY node/package*.json ./node/

# Install Node deps inside /node
RUN cd node && npm install --omit=dev

# Copy full source
COPY . .

# Install Python deps
RUN pip install -r python/requirements.txt

ENV PORT=3000
EXPOSE 3000

# 🔥 IMPORTANT: run index.js from node folder
CMD ["node", "node/index.js"]
