# Stage 1: Builder
# DEVOPS: python:3.10 即将 EOL（2026-10），升级到 3.12-slim（安全补丁最新，性能提升）
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
# DEVOPS: 与 builder 保持一致，python:3.12-slim
FROM python:3.12-slim

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

# P2-30: 分层优化 — 先复制不常变的 app/ 源码，再复制 binaries/（ZLM 二进制）
# 这样 app 代码变更时不会重新复制 binaries（约 50MB），加速构建。
# 生产推荐：将 ZLM 剥离为独立 sidecar 容器（见 docker-compose.yml 的 zlm 服务），
# 此处保留 binaries 仅为单容器部署兼容。
COPY app/ ./app/

# ZLM 二进制（可选 — 生产推荐 sidecar 部署）
COPY binaries/ ./binaries/

# 配置文件与入口脚本
COPY alembic.ini initial_data.py ./
COPY alembic/ ./alembic/
COPY bin/ ./bin/
COPY tools/ ./tools/

# FIXED-P0: S-06-05 chmod移到COPY之后执行，否则文件尚不存在chmod永远不生效
RUN if [ -f /app/binaries/linux64/MediaServer ]; then chmod +x /app/binaries/linux64/MediaServer; fi || true

RUN mkdir -p /app/data /app/logs /app/records && chown -R appuser:appuser /app/data /app/logs /app/records

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# FIXED: [2026-07-10] 补充 5061/tcp（SIP TLS），与 docker-compose.yml ports 映射一致 [全栈工程师]
# FIXED: RTP端口范围与docker-compose.yml保持一致，使用30000-30100而非30000-39000
EXPOSE 8000 5060/udp 5060/tcp 5061/tcp 30000-30999/udp 8880 1935 554

# FIXED D-05: 统一健康检查端点为 /api/v1/health/
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ || exit 1

USER appuser

CMD ["sh", "-c", "python app/initial_data.py && python -m app.main"]
