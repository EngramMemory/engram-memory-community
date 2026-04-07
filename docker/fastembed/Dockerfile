# ── Stage 1: Build ──────────────────────────────────────────────────
# Install all dependencies in a full image, then copy site-packages out.
FROM python:3.10-slim AS builder

WORKDIR /build

ARG EMBED_BACKEND=fastembed

# Single layer: shared + backend-specific deps
RUN pip install --no-cache-dir --prefix=/install \
        fastapi>=0.104.0 \
        uvicorn>=0.42.0 \
        numpy>=1.21.0 && \
    if [ "$EMBED_BACKEND" = "sentence-transformers" ]; then \
        pip install --no-cache-dir --prefix=/install \
            torch --index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir --prefix=/install \
            sentence-transformers>=2.2.0 einops; \
    else \
        pip install --no-cache-dir --prefix=/install fastembed==0.2.7; \
    fi && \
    # Strip tests, caches, and unnecessary files from installed packages
    find /install -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
    find /install -type d -name "tests" -exec rm -rf {} + 2>/dev/null; \
    find /install -type d -name "test" -exec rm -rf {} + 2>/dev/null; \
    find /install -type f -name "*.pyc" -delete 2>/dev/null; \
    find /install -type f -name "*.pyo" -delete 2>/dev/null; \
    true

# ── Stage 2: Runtime ───────────────────────────────────────────────
# Minimal image with only the installed packages + service code.
FROM python:3.10-slim

WORKDIR /app

ARG EMBED_BACKEND=fastembed
ENV EMBED_BACKEND=${EMBED_BACKEND} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Single layer: curl for healthcheck + cleanup
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy only installed Python packages from builder
COPY --from=builder /install /usr/local

COPY fastembed_service.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "fastembed_service:app", "--host", "0.0.0.0", "--port", "8000"]
