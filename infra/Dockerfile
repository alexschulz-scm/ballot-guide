# Ballot Guide API — Production Dockerfile
# Build context: repo root (run with: docker build -f infra/Dockerfile .)

FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY apps/ apps/
COPY mcp_servers/ mcp_servers/
COPY scripts/ scripts/
COPY data/ data/

# Create data directory for SQLite
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
