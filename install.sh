#!/usr/bin/env bash
# =============================================================================
# PyGBSentry 一键安装脚本（Linux / macOS）
# 适用：全新部署、快速体验（SQLite 模式，无需 PostgreSQL / Redis / Node）
# 用法：
#   bash install.sh                 # 交互式安装（默认 SQLite 快速模式）
#   bash install.sh --mirror        # 使用清华 PyPI 镜像（国内推荐）
#   bash install.sh --with-frontend # 同时构建前端（需要 Node.js 18+）
# 安装完成后运行：./start.sh   然后浏览器打开 http://localhost:8000
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

MIRROR=0; WITH_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --mirror) MIRROR=1 ;;
    --with-frontend) WITH_FRONTEND=1 ;;
    *) warn "未知参数 $arg（忽略）" ;;
  esac
done

cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"

echo -e "${GREEN}=============================================="
echo -e "   PyGBSentry 一键安装（SQLite 快速模式）"
echo -e "==============================================${NC}"

# ---------------------------------------------------------------- 1. Python
info "步骤 1/6 检查 Python（需要 3.11 ~ 3.13）..."

PY_BIN=""
for cand in python3.12 python3.11 python3.13 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    VER=$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
    MAJOR=$(echo "$VER" | cut -d. -f1); MINOR=$(echo "$VER" | cut -d. -f2)
    if [ "$MAJOR" = "3" ] && [ "$MINOR" -ge 11 ] && [ "$MINOR" -le 13 ] 2>/dev/null; then
      PY_BIN="$cand"; ok "找到 Python $VER（$cand）"; break
    fi
  fi
done

if [ -z "$PY_BIN" ]; then
  DETECTED=$( (python3 -V 2>/dev/null || python -V 2>/dev/null) || echo "未找到" )
  fail "未找到合适的 Python。当前检测到：$DETECTED

本项目要求 Python 3.11 ~ 3.13（3.8/3.9/3.10 无法运行，会报语法错误）。

安装方法：
  Ubuntu/Debian:  sudo apt update && sudo apt install -y python3.12 python3.12-venv
  CentOS/RHEL:    sudo dnf install -y python3.12
  macOS:          brew install python@3.12
  Windows:        https://www.python.org/downloads/（安装时勾选 Add to PATH）
  国内镜像:       https://mirrors.huaweicloud.com/python/
然后重新运行本脚本：bash install.sh"
fi

# ---------------------------------------------------------------- 2. 虚拟环境
info "步骤 2/6 创建 Python 虚拟环境..."
cd "$BACKEND_DIR"
if [ ! -d "$VENV_DIR" ]; then
  "$PY_BIN" -m venv venv || fail "创建虚拟环境失败（Ubuntu 需先安装 python3-venv：sudo apt install -y python3.12-venv）"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
ok "虚拟环境就绪（$VENV_DIR）"

# ---------------------------------------------------------------- 3. 依赖
info "步骤 3/6 安装后端依赖（约 1-3 分钟）..."
PIP_ARGS=()
if [ "$MIRROR" = "1" ]; then
  PIP_ARGS=(-i https://pypi.tuna.tsinghua.edu.cn/simple)
  info "使用清华 PyPI 镜像"
fi
pip install --upgrade pip "${PIP_ARGS[@]}" >/dev/null 2>&1 || true
pip install -r requirements.txt "${PIP_ARGS[@]}" || fail "依赖安装失败。国内网络建议：bash install.sh --mirror"
ok "后端依赖安装完成"

# ---------------------------------------------------------------- 4. 配置 .env
info "步骤 4/6 生成配置文件 .env ..."
if [ -f ".env" ]; then
  warn ".env 已存在，保留现有配置（不覆盖）"
else
  cp .env.example .env
  # 快速模式：SQLite（免 PG/Redis）+ 自动生成密钥
  GEN_HEX=$("$PY_BIN" -c 'import secrets; print(secrets.token_hex(32))')
  GEN_HEX2=$("$PY_BIN" -c 'import secrets; print(secrets.token_hex(32))')
  GEN_PWD=$("$PY_BIN" -c 'import secrets; print(secrets.token_urlsafe(9))')
  # 管理员密码：用户自设或自动生成（写入凭据文件）
  printf "设置管理员密码（直接回车 = 自动生成）: "
  read -r ADMIN_PWD_INPUT
  ADMIN_PWD="${ADMIN_PWD_INPUT:-$GEN_PWD}"
  if [ "$(uname)" = "Darwin" ]; then
    sed -i '' 's|^DATABASE_TYPE=postgresql|DATABASE_TYPE=sqlite|' .env
    sed -i '' "s|^SECRET_KEY=.*|SECRET_KEY=\"$GEN_HEX\"|" .env
    sed -i '' "s|^FIELD_ENCRYPTION_KEY=.*|FIELD_ENCRYPTION_KEY=\"$GEN_HEX2\"|" .env
    sed -i '' "s|^ADMIN_INITIAL_PASSWORD=.*|ADMIN_INITIAL_PASSWORD=\"$ADMIN_PWD\"|" .env
    grep -q '^ADMIN_INITIAL_PASSWORD=' .env || printf 'ADMIN_INITIAL_PASSWORD="%s"\n' "$ADMIN_PWD" >> .env
  else
    sed -i 's|^DATABASE_TYPE=postgresql|DATABASE_TYPE=sqlite|' .env
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=\"$GEN_HEX\"|" .env
    sed -i "s|^FIELD_ENCRYPTION_KEY=.*|FIELD_ENCRYPTION_KEY=\"$GEN_HEX2\"|" .env
    sed -i "s|^ADMIN_INITIAL_PASSWORD=.*|ADMIN_INITIAL_PASSWORD=\"$ADMIN_PWD\"|" .env
    grep -q '^ADMIN_INITIAL_PASSWORD=' .env || printf 'ADMIN_INITIAL_PASSWORD="%s"\n' "$ADMIN_PWD" >> .env
  fi
  printf 'PyGBSentry 管理员账号\n\n用户名: admin\n密码:   %s\n\n请妥善保管，登录后可在平台内修改。\n' "$ADMIN_PWD" > "$ROOT_DIR/管理员密码.txt"
  ok ".env 已生成（SQLite 快速模式），凭据已保存到 管理员密码.txt"
fi
# 从 .env 提取管理员密码用于最终展示
ADMIN_PWD=$(grep -E '^ADMIN_INITIAL_PASSWORD=' .env | head -1 | sed 's/^ADMIN_INITIAL_PASSWORD=//; s/^"//; s/"$//')
[ -n "$ADMIN_PWD" ] || ADMIN_PWD="(见 .env 的 ADMIN_INITIAL_PASSWORD；若为空则首次启动随机生成，见启动日志)"

# 端口冲突自避：8000 被占则依次尝试 8010/8080/8888/9000
PORT=$(grep -E '^BACKEND_PUBLIC_PORT=' .env | head -1 | cut -d= -f2)
PORT=${PORT:-8000}
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$PORT "; then
  for ALT in 8010 8080 8888 9000; do
    if ! ss -tln 2>/dev/null | grep -q ":$ALT "; then
      if [ "$(uname)" = "Darwin" ]; then
        sed -i '' "s|^BACKEND_PUBLIC_PORT=.*|BACKEND_PUBLIC_PORT=$ALT|" .env
      else
        sed -i "s|^BACKEND_PUBLIC_PORT=.*|BACKEND_PUBLIC_PORT=$ALT|" .env
      fi
      PORT=$ALT
      ok "端口 8000 被占用，已自动切换为 $PORT（写入 .env）"
      break
    fi
  done
fi

# ---------------------------------------------------------------- 5. 初始化数据库
info "步骤 5/6 初始化数据库（建表 + 默认管理员）..."
python app/initial_data.py || fail "数据库初始化失败，请把上方完整报错发到 issue"
ok "数据库初始化完成"

# ---------------------------------------------------------------- 6. 前端（可选）
if [ "$WITH_FRONTEND" = "1" ]; then
  info "步骤 6/6 构建前端..."
  if [ -d "$ROOT_DIR/frontend/dist" ] && [ -n "$(ls -A "$ROOT_DIR/frontend/dist" 2>/dev/null)" ]; then
    ok "frontend/dist 已存在，跳过构建（如需重建请先删除 dist）"
  elif command -v node >/dev/null 2>&1; then
    cd "$ROOT_DIR/frontend"
    if [ -f pnpm-lock.yaml ] && command -v pnpm >/dev/null 2>&1; then
      pnpm install && pnpm build
    else
      npm install && npm run build
    fi
    ok "前端构建完成（frontend/dist）"
  else
    warn "未检测到 Node.js 18+，跳过前端构建。可安装 Node 后运行：cd frontend && npm install && npm run build"
  fi
  cd "$ROOT_DIR"
else
  info "步骤 6/6 跳过前端构建（使用 --with-frontend 可一并构建）"
fi

# ---------------------------------------------------------------- 完成
echo -e "${GREEN}"
echo "=============================================="
echo "   ✔ 安装完成！"
echo "==============================================${NC}"
echo ""
echo "  启动：      ./start.sh"
echo "  平台地址：  http://localhost:$PORT          （完整管理界面，浏览器直接打开）"
echo "  API 文档：  http://localhost:$PORT/docs"
echo "  管理员密码：已保存到 管理员密码.txt"
echo "  管理员账号：admin"
echo "  管理员密码：$ADMIN_PWD   （首次登录后请修改）"
echo ""
echo "  生产部署（PostgreSQL/Redis/Nginx/HTTPS）：docs/INSTALL.md"
echo "  遇到问题：  https://gitee.com/suoten/PyGBSentry/issues"
echo ""
