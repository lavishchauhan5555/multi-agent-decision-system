# -----------------------------
# Base Image (Node 20 + Python 3.11)
# -----------------------------
FROM node:20-bookworm

# Install Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# App Setup
# -----------------------------
WORKDIR /app
COPY . .

# -----------------------------
# Node Backend
# -----------------------------
WORKDIR /app/server
RUN npm install

# -----------------------------
# FastAPI (Python)
# -----------------------------
WORKDIR /app/orchestrator

RUN python3 -m venv /app/venv
RUN /app/venv/bin/pip install --upgrade pip
RUN /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# -----------------------------
# React Frontend (Vite)
# -----------------------------
WORKDIR /app/client
RUN npm install
RUN npm run build

# -----------------------------
# Start Script
# -----------------------------
WORKDIR /app
RUN chmod +x start.sh

EXPOSE 10000

CMD ["./start.sh"]