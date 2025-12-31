FROM python:3.11-slim

# Install Node and dependencies
RUN apt-get update && apt-get install -y curl build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs python3-dev python3-pip

WORKDIR /app

# Copy Node files and install dependencies
COPY node/package*.json ./node/
RUN cd node && npm install --omit=dev

# Copy Python requirements and install for python3
COPY python/requirements.txt ./python/
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -r python/requirements.txt

# Copy rest of project
COPY . .

# Optional: make 'python' point to 'python3' for Node scripts
RUN ln -s /usr/local/bin/python3 /usr/local/bin/python

CMD ["node", "alerts.js"]
