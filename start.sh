#!/bin/bash
set -x

echo "Starting FastAPI..."
cd /app/orchestrator || exit 1
/app/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

echo "Starting Node server..."
cd /app/server || exit 1
node server.js &
NODE_PID=$!

echo "FastAPI PID=$FASTAPI_PID"
echo "Node PID=$NODE_PID"

wait -n

echo "One service stopped. Showing process status..."
ps aux

echo "Shutting down..."
kill $FASTAPI_PID $NODE_PID || true