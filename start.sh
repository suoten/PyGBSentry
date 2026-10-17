#!/usr/bin/env bash
# PyGBSentry 启动脚本（Linux / macOS）：激活虚拟环境并启动后端
# 前台运行，Ctrl+C 停止；生产建议 docs/INSTALL.md 的 systemd/Nginx 方案
cd "$(dirname "$0")/backend"

if [ ! -d "venv" ]; then
  echo "[启动失败] 未找到虚拟环境，请先运行：bash install.sh"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PORT=$(grep -E '^BACKEND_PUBLIC_PORT=' .env 2>/dev/null | head -1 | cut -d= -f2)
PORT=${PORT:-8000}

echo "[PyGBSentry] 启动后端 → http://localhost:$PORT"
echo "[PyGBSentry] API 文档 → http://localhost:$PORT/docs"
exec python -m app.main
