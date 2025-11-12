#!/bin/bash

# Start script for Background Removal Telegram Bot
# This script is designed to be used with systemd or as a standalone launcher

set -e

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "Error: .env file not found!"
    exit 1
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Warning: Virtual environment not found at venv/"
    echo "Make sure Python packages are installed globally or create a venv"
fi

# Check if database is accessible
echo "Checking database connection..."
python -c "from app.database import get_db; import asyncio; asyncio.run(get_db().check_connection())" 2>/dev/null || {
    echo "Warning: Database connection check failed. Bot will attempt to connect on startup."
}

# Run database migrations
echo "Running database migrations..."
alembic upgrade head || {
    echo "Warning: Migration failed. Check database connectivity."
}

# Start the bot
echo "Starting Background Removal Bot..."
exec python -m app.bot
