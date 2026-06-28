# =============================================================================
# OptiStock Production Dockerfile for Google Cloud Run
# Multi-stage build optimized for asia-south1 deployment
# =============================================================================

# Stage 1: Builder - Compile dependencies
FROM python:3.11-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PYTHONDONTWRITEBYTECODE=1

# Install build dependencies for Prophet
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.cloudrun.txt requirements.txt
RUN pip install --target=/build/deps -r requirements.txt

# Stage 2: Production Runtime
FROM python:3.11-slim-bookworm

# Cloud Run expects PORT env var
ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Copy Python packages from builder
COPY --from=builder /build/deps /usr/local/lib/python3.11/site-packages

# Copy application code
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser data/ ./data/

# Switch to non-root user
USER appuser

# Cloud Run health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port (Cloud Run uses PORT env var)
EXPOSE 8080

# Run FastAPI with uvicorn (using python -m for target-installed packages)
CMD exec python -m uvicorn src.api:app --host 0.0.0.0 --port ${PORT} --workers 1
