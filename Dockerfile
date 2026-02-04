FROM python:3.11-slim

# Install system deps for WeasyPrint and Playwright
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 libpq-dev gcc \
    # Playwright dependencies
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY templates/ ./templates/

# Install dependencies
RUN uv sync --frozen --no-dev

# Install Playwright browsers (chromium only to save space)
RUN uv run playwright install chromium

# Expose port
EXPOSE 8000

# Run API - use PORT env var for Railway compatibility
CMD ["sh", "-c", "uv run uvicorn hr_breaker.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
