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

if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$PORT "; then
  echo "[INFO] PyGBSentry 已在运行：http://localhost:$PORT"
  command -v xdg-open >/dev/null 2>&1 && xdg-open "http://localhost:$PORT" >/dev/null 2>&1
  exit 0
fi

echo "[PyGBSentry] 启动后端 → http://localhost:$PORT （完整管理界面）"
echo "[PyGBSentry] API 文档 → http://localhost:$PORT/docs"
echo "[PyGBSentry] 停止服务 → ./stop.sh （或 Ctrl+C）"
command -v xdg-open >/dev/null 2>&1 && (sleep 8 && xdg-open "http://localhost:$PORT" >/dev/null 2>&1 &)
exec python -m app.main
