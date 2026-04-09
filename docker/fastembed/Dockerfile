# ── Stage 1: Build ──────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# fastembed 0.7.4 uses ONNX Runtime with native ARM64/Apple Silicon support
# No PyTorch or sentence-transformers needed
RUN pip install --no-cache-dir \
        fastembed==0.7.4 \
        fastapi>=0.115.0 \
        uvicorn>=0.34.0 \
        numpy>=1.26.0

# Strip bloat from installed packages
RUN find /usr/local/lib/python3.12/site-packages -type d \( -name "__pycache__" -o -name "tests" -o -name "test" -o -name "benchmarks" -o -name "docs" \) -exec rm -rf {} + 2>/dev/null; \
    find /usr/local/lib/python3.12/site-packages -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyi" \) -delete 2>/dev/null; \
    true

# ── Stage 2: Runtime ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY fastembed_service.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "fastembed_service:app", "--host", "0.0.0.0", "--port", "8000"]
