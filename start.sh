#!/bin/bash

# Start FastAPI
echo "Starting FastAPI..."
cd /app/orchestrator
/app/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Start Node
echo "Starting Node server..."
cd /app/server
node server.js &
NODE_PID=$!   

# Wait for any process to exit
wait -n

# If one crashes → stop both
echo "One service stopped. Shutting down..."
kill -TERM $FASTAPI_PID $NODE_PID 