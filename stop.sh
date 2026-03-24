#!/bin/bash

echo "Checking for running instances..."

# Check Local (default dev port in main.py / run.sh)
if lsof -i:6001 -t >/dev/null ; then
    PID=$(lsof -t -i:6001)
    echo "Found LOCAL process on port 6001 (PID $PID). Stopping..."
    kill $PID
    echo "Local process stopped."
else
    echo "No LOCAL process found on port 6001."
fi

# Check Docker
if docker compose version >/dev/null 2>&1; then
    CMD="docker compose"
else
    CMD="docker-compose"
fi

# We use 'ps -q' to see if any containers from this compose project are running
if [ -n "$($CMD ps -q)" ]; then
    echo "Found RUNNING Docker containers. Stopping..."
    $CMD stop
    echo "Docker containers stopped."
else
    echo "No Docker containers running."
fi
