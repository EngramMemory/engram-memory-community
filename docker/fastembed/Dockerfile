FROM python:3.10-slim

WORKDIR /app

# EMBED_BACKEND: "fastembed" (x86, ONNX) or "sentence-transformers" (ARM64, PyTorch)
ARG EMBED_BACKEND=fastembed
ENV EMBED_BACKEND=${EMBED_BACKEND}

# Shared dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.104.0 \
    uvicorn>=0.42.0 \
    numpy>=1.21.0

# Backend-specific dependencies
RUN if [ "$EMBED_BACKEND" = "sentence-transformers" ]; then \
        pip install --no-cache-dir \
            torch --index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir \
            sentence-transformers>=2.2.0 \
            einops; \
    else \
        pip install --no-cache-dir fastembed==0.2.7; \
    fi

RUN apt-get update -qq && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY fastembed_service.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "fastembed_service:app", "--host", "0.0.0.0", "--port", "8000"]
