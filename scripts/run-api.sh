#!/bin/bash
# Run the FastAPI backend server

set -e

cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run with uvicorn
uv run uvicorn hr_breaker.api.main:app --reload --host 0.0.0.0 --port 8000
