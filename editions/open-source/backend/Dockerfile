# Stage 1: Builder
FROM python:3.10-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# FIXED: ZLM binary copy is conditional — if binaries/linux64/MediaServer exists it will be
# included by the `COPY . .` below; chmod only if present to avoid build failure.
RUN mkdir -p /app/binaries/linux64 && \
    if [ -f /app/binaries/linux64/MediaServer ]; then chmod +x /app/binaries/linux64/MediaServer; fi || true

COPY . .

RUN mkdir -p /app/data /app/logs /app/records && chown -R appuser:appuser /app/data /app/logs /app/records

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# FIXED: RTP端口范围与docker-compose.yml保持一致，使用30000-30199而非30000-39000
EXPOSE 8000 5060/udp 5060/tcp 30000-30199/udp 8880 1935 554

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ || exit 1

USER appuser

CMD ["sh", "-c", "python app/initial_data.py && python -m app.main"]
