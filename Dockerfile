FROM python:3.11-slim

# Install system deps for WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY templates/ ./templates/

# Install dependencies
RUN uv sync --frozen --no-dev

# Expose port
EXPOSE 8000

# Run API
CMD ["uv", "run", "uvicorn", "hr_breaker.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
