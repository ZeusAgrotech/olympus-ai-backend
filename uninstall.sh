#!/bin/bash

show_help() {
    echo "Usage: ./uninstall.sh [OPTIONS]"
    echo "Options: (You must specify exactly one check)"
    echo "  -l, --local   Uninstall local artifacts (.venv, __pycache__)"
    echo "  -D, --docker  Uninstall Docker resources"
    exit 1
}

MODE=""

for arg in "$@"
do
    case $arg in
        -l|--local)
        MODE="local"
        ;;
        -D|--docker)
        MODE="docker"
        ;;
    esac
done

if [ -z "$MODE" ]; then
    echo "Error: You must specify --local or --docker."
    show_help
fi

echo "Uninstalling/Cleaning up ($MODE)..."

if [ "$MODE" = "docker" ]; then
    # 1. Docker Cleanup
    if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker compose"
    elif docker-compose --version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker-compose"
    else
        DOCKER_COMPOSE_CMD=""
    fi

    if [ -n "$DOCKER_COMPOSE_CMD" ]; then
        echo "Removing Docker resources..."
        $DOCKER_COMPOSE_CMD down --rmi all -v
    else
        echo "Docker Compose not found, skipping Docker cleanup."
    fi

elif [ "$MODE" = "local" ]; then
    # 2. Local Cleanup
    echo "Removing local environment (.venv) and caches..."
    rm -rf .venv

    # Remove files, suppressing errors initially
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

    # Check if there are still pycache files left (likely owned by root)
    if [ -d "__pycache__" ] || find . -name "__pycache__" | grep -q "__pycache__"; then
         echo "Warning: Some __pycache__ files are owned by root (from Docker)."
         echo "Requesting sudo permission to remove them..."
         
         sudo find . -type d -name "__pycache__" -exec rm -rf {} +
         
         if [ $? -eq 0 ]; then
            echo "Root-owned files removed successfully."
         else
            echo "Failed to remove some files. You may need to remove them manually."
         fi
    fi
fi

echo "Cleanup complete."
