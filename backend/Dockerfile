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

ARG BUILD_VERSION=dev
ENV BUILD_VERSION=${BUILD_VERSION}

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

COPY . .

# FIXED-P0: S-06-05 chmod移到COPY之后执行，否则文件尚不存在chmod永远不生效
RUN if [ -f /app/binaries/linux64/MediaServer ]; then chmod +x /app/binaries/linux64/MediaServer; fi || true

RUN mkdir -p /app/data /app/logs /app/records && chown -R appuser:appuser /app/data /app/logs /app/records

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# FIXED: RTP端口范围与docker-compose.yml保持一致，使用30000-30199而非30000-39000
EXPOSE 8000 5060/udp 5060/tcp 30000-30999/udp 8880 1935 554

# FIXED D-05: 统一健康检查端点为 /api/v1/health/
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ || exit 1

USER appuser

CMD ["sh", "-c", "python app/initial_data.py && python -m app.main"]
