FROM node:22-bullseye

# ---- Install Python 3.11 ----
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 python3.11-distutils python3-pip \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && python --version

WORKDIR /app

# ---- Node deps ----
COPY node/package*.json ./node/
RUN cd node && npm install --omit=dev

# ---- App source ----
COPY . .

# ---- Python deps ----
RUN pip install --upgrade pip \
    && pip install -r python/requirements.txt

ENV PORT=3000
EXPOSE 3000

CMD ["node", "node/index.js"]
