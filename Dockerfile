FROM node:22-bullseye

# Install python
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Node deps
COPY node/package*.json ./
RUN npm install --omit=dev

# App code
COPY . .

# Python deps
RUN pip install -r python/requirements.txt

ENV PORT=3000
EXPOSE 3000

CMD ["node", "index.js"]
