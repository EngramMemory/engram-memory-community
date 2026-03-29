FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastembed==0.2.7 \
    fastapi>=0.104.0 \
    uvicorn>=0.42.0 \
    numpy>=1.21.0

COPY fastembed_service.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "fastembed_service:app", "--host", "0.0.0.0", "--port", "8000"]
