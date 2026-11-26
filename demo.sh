#!/usr/bin/env bash
# =============================================================================
# PyGBSentry 一键体验（Docker + 内置设备模拟器）
# 无需任何摄像头：2 台模拟 NVR 自动注册，点播即出测试卡画面。
#
# 用法：
#   bash demo.sh              # 一键启动（自动生成 .env、自动配置 SDP IP）
#   bash demo.sh --stop       # 停止全部服务
#   bash demo.sh --down       # 停止并删除容器（保留数据卷）
#
# 完成后浏览器打开：http://<本机IP>/
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

cd "$(dirname "$0")"

STOP=0; DOWN=0
for arg in "$@"; do
  case "$arg" in
    --stop) STOP=1 ;;
    --down) DOWN=1 ;;
    *) warn "未知参数 $arg（忽略）" ;;
  esac
done

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.simulator.yml"

if [ "$STOP" = "1" ]; then
  $COMPOSE stop
  ok "全部服务已停止（数据保留）。重新启动：bash demo.sh"
  exit 0
fi
if [ "$DOWN" = "1" ]; then
  $COMPOSE down
  ok "容器已删除（数据卷保留）。"
  exit 0
fi

# ---------------------------------------------------------------- 0. 环境检查
command -v docker >/dev/null 2>&1 || fail "未安装 Docker：https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || fail "Docker 引擎未运行，请先启动 Docker Desktop"
docker compose version >/dev/null 2>&1 || fail "缺少 docker compose 插件（Docker 20.10+ 自带）"
info "Docker 环境就绪"

# ---------------------------------------------------------------- 1. 准备 .env
if [ ! -f .env ]; then
  info "首次运行：生成 .env（随机密钥 + 强口令）"
  LAN_IP=$(python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('223.5.5.5', 53))
print(s.getsockname()[0])
s.close()" 2>/dev/null || echo "127.0.0.1")
  SIP_PWD="Sip$(python -c "import secrets; print(secrets.token_urlsafe(12))" | tr -d '-_')7k"
  cat > .env <<EOF
POSTGRES_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(18))")
REDIS_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(18))")
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
FIELD_ENCRYPTION_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
MEDIA_SERVER_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
BACKEND_PUBLIC_HOST=${LAN_IP}
SIP_DEFAULT_PASSWORD=${SIP_PWD}
SIM_DEVICE_PASSWORD=${SIP_PWD}
ENABLE_AUTO_DISCOVERY=true
BACKEND_CORS_ORIGINS=[]
EOF
  ok ".env 已生成（BACKEND_PUBLIC_HOST=${LAN_IP}）"
else
  # 补齐演示必需项（不动用户已有值）
  grep -q "^ENABLE_AUTO_DISCOVERY=" .env  || echo "ENABLE_AUTO_DISCOVERY=true"  >> .env
  grep -q "^BACKEND_CORS_ORIGINS=" .env   || echo "BACKEND_CORS_ORIGINS=[]"    >> .env
  if ! grep -q "^SIM_DEVICE_PASSWORD=" .env; then
    warn ".env 缺少 SIM_DEVICE_PASSWORD（模拟器设备密码），请确认其与 SIP_DEFAULT_PASSWORD 一致"
    grep -q "^SIP_DEFAULT_PASSWORD=" .env && \
      echo "SIM_DEVICE_PASSWORD=$(grep '^SIP_DEFAULT_PASSWORD=' .env | cut -d= -f2)" >> .env
  fi
  ok ".env 已就绪（保留现有配置）"
fi

# ---------------------------------------------------------------- 2. 启动
# 优先拉取 ghcr.io 预构建镜像（快）；镜像缺失/拉取失败时自动本地构建兜底
info "启动全栈（首次会拉取/构建镜像：预构建镜像约 3~5 分钟，本地构建约 10~30 分钟）"
$COMPOSE up -d
ok "容器已启动"

# ---------------------------------------------------------------- 3. 等待 backend
info "等待 backend 就绪（约 1~2 分钟）..."
for i in $(seq 1 40); do
  if docker exec pygbsentry-backend-1 curl -sf http://localhost:8000/api/v1/health/ >/dev/null 2>&1; then
    break
  fi
  sleep 5
  [ "$i" = "40" ] && warn "backend 仍在启动中，可稍后手动查看：docker logs pygbsentry-backend-1"
done

# backend 重启后 zlm 需要重挂 netns（Docker service 网络模式特性）
docker restart pygbsentry-zlm >/dev/null 2>&1 || true
sleep 15

# ---------------------------------------------------------------- 4. 自动修复 SDP IP（绕开 UDP hairpin）
info "自动配置媒体节点 SDP IP 为 backend 容器 IP（绕开 Docker Desktop UDP 回环丢包）"
BACKEND_IP=$(docker inspect pygbsentry-backend-1 --format '{{index .NetworkSettings.Networks "pygbsentry_frontend" "IPAddress"}}' 2>/dev/null || echo "")
if [ -n "$BACKEND_IP" ]; then
  docker exec pygbsentry-db-1 psql -U postgres -d pygb28181 -c \
    "UPDATE media_nodes SET sdp_ip='${BACKEND_IP}', stream_ip='${BACKEND_IP}' WHERE sdp_ip IS DISTINCT FROM '${BACKEND_IP}';" >/dev/null 2>&1 \
    && ok "SDP IP 已设置为 ${BACKEND_IP}" \
    || warn "SDP IP 自动配置失败（不影响信令；点播无流时见 README 排查表手动设置）"
fi

# ---------------------------------------------------------------- 5. 清理可能的黑名单
docker exec pygbsentry-db-1 psql -U postgres -d pygb28181 -c "DELETE FROM ip_blacklist;" >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 6. 完成提示
LAN_IP=$(grep '^BACKEND_PUBLIC_HOST=' .env | cut -d= -f2)
ADMIN_PWD=$(MSYS_NO_PATHCONV=1 docker exec pygbsentry-backend-1 cat /app/data/.admin_initial_password 2>/dev/null || echo "（见容器 /app/data/.admin_initial_password）")
echo -e "${GREEN}=============================================="
echo -e "   部署完成！设备模拟器正在运行"
echo -e "==============================================${NC}"
echo "  管理后台 : http://${LAN_IP}/"
echo "  登录账号 : admin / ${ADMIN_PWD}"
echo "  模拟设备 : 34020000001310000001 / 34020000001310000002（各 2 通道）"
echo
echo "  👉 在「设备列表」点击任意通道播放，即可看到测试卡画面"
echo
echo "  常用命令："
echo "    bash demo.sh --stop     停止服务"
echo "    bash demo.sh --down     删除容器（保留数据）"
echo "    docker logs pygbsentry-device-simulator   查看模拟设备日志"
echo "    docker logs pygbsentry-backend-1          查看平台日志"
