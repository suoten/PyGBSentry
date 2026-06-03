#!/usr/bin/env bash
# 构建开源版绿色包：backend + frontend/dist + run.sh + run.bat，产出 zip。
# 用法：在 editions/open-source 目录下执行 ./scripts/build-green-package.sh
# 或从仓库根目录：cd editions/open-source && ./scripts/build-green-package.sh
set -e

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少依赖命令：$1。请先安装后重试。"
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

need_cmd node
need_cmd npm
need_cmd python
need_cmd zip
need_cmd rsync

# Sanity check: required docs/tools must exist
[ -f "docs/PREBUILT.md" ] || fail "缺少 docs/PREBUILT.md（绿色包说明）"
[ -f "docs/RUNTIME_QUERY_CHEATSHEET.md" ] || fail "缺少 docs/RUNTIME_QUERY_CHEATSHEET.md（运维速查表）"
[ -f "tools/query_runtime_events.py" ] || fail "缺少 tools/query_runtime_events.py（运维查询脚本）"

echo "==> Verify runtime plugin coverage..."
python tools/check_runtime_coverage.py || fail "runtime 覆盖率自检失败（tools/check_runtime_coverage.py）"

VERSION="${VERSION:-1.0.0}"
SUFFIX="${SUFFIX:-}"
if [ -n "$SUFFIX" ]; then
  OUT_NAME="PyGBSentry-oss-${VERSION}-${SUFFIX}"
else
  OUT_NAME="PyGBSentry-oss-${VERSION}"
fi
OUT_DIR="./dist-green"
ARCHIVE="${OUT_NAME}.zip"

echo "==> Building frontend..."
cd frontend
npm ci 2>/dev/null || npm install || fail "前端依赖安装失败（npm install）。"
npm run build || fail "前端构建失败（npm run build）。"
cd ..

echo "==> Preparing green package in $OUT_DIR/$OUT_NAME..."
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/$OUT_NAME"

# 后端（排除 venv、__pycache__、.env、.git）
rsync -a --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='.git' \
  backend/ "$OUT_DIR/$OUT_NAME/backend/"
# 前端构建产物
cp -r frontend/dist "$OUT_DIR/$OUT_NAME/frontend-dist"
# 一键运行脚本与说明
cp run.sh run.bat start-frontend.sh start-frontend.bat "$OUT_DIR/$OUT_NAME/"
cp docs/PREBUILT.md "$OUT_DIR/$OUT_NAME/" 2>/dev/null || true
cp docs/RUNTIME_QUERY_CHEATSHEET.md "$OUT_DIR/$OUT_NAME/" 2>/dev/null || true
mkdir -p "$OUT_DIR/$OUT_NAME/tools" 2>/dev/null || true
cp tools/query_runtime_events.py "$OUT_DIR/$OUT_NAME/tools/" 2>/dev/null || true
cp tools/check_runtime_coverage.py "$OUT_DIR/$OUT_NAME/tools/" 2>/dev/null || true
cat > "$OUT_DIR/$OUT_NAME/README-绿色包.txt" << 'EOF'
PyGBSentry 开源版绿色包
======================
1. 本机需安装 Python 3.10+，数据库（如 PostgreSQL/SQLite）与 ZLMediaKit 需自行配置。
2. 启动后端：运行 run.sh（Linux/macOS）或 run.bat（Windows），将自动创建虚拟环境并安装依赖，默认 http://0.0.0.0:8000。
3. 启动前端静态服务：运行 start-frontend.sh（Linux/macOS）或 start-frontend.bat（Windows），默认端口 8080（可通过环境变量 PORT 覆盖）。
4. 如需使用 Nginx：将 frontend-dist 目录配置为静态服务根目录。
5. 详细说明见 PREBUILT.md；运维查询速查表见 RUNTIME_QUERY_CHEATSHEET.md。
EOF

echo "==> Creating $ARCHIVE..."
cd "$OUT_DIR"
zip -r "../$ARCHIVE" "$OUT_NAME" >/dev/null || fail "打包失败（zip）。"
cd ..
rm -rf "$OUT_DIR"
echo "==> Done: $ARCHIVE"
