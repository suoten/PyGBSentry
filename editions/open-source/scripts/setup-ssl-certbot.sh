#!/usr/bin/env bash
#
# setup-ssl-certbot.sh — 一键配置 Let's Encrypt + nginx HTTPS 反代
#
# 前置条件：
#   1. 域名 pygbsentry.jjtt.net 已解析到本机公网IP
#   2. 80 端口可从外网访问（Let's Encrypt HTTP-01 验证需要）
#   3. nginx 已安装
#
# 用法：
#   sudo bash scripts/setup-ssl-certbot.sh
#

set -euo pipefail

DOMAIN="${1:-pygbsentry.jjtt.net}"
EMAIL="${2:-admin@${DOMAIN}}"
WEBROOT="/var/www/certbot"
NGINX_CONF_DIR="/etc/nginx/conf.d"
NGINX_AVAILABLE_DIR="/etc/nginx/sites-available"  # Debian/Ubuntu
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"

echo "=== PyGBSentry SSL 自动配置 ==="
echo "域名: ${DOMAIN}"
echo "邮箱: ${EMAIL}"
echo ""

# 1. 安装 certbot
echo "[1/5] 安装 certbot..."
if command -v apt-get &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx
elif command -v yum &>/dev/null; then
    yum install -y certbot python3-certbot-nginx
elif command -v dnf &>/dev/null; then
    dnf install -y certbot python3-certbot-nginx
else
    echo "不支持的包管理器，请手动安装 certbot"
    exit 1
fi

# 2. 创建 webroot 目录
echo "[2/5] 创建 certbot webroot 目录..."
mkdir -p "${WEBROOT}"

# 3. 生成 nginx 临时配置（仅80端口，用于证书申请）
echo "[3/5] 生成 nginx 临时配置..."
cat > /tmp/pygbsentry-http-only.conf <<'NGINX_EOF'
server {
    listen 80;
    server_name _DOMAIN_;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 "certbot verification placeholder";
        add_header Content-Type text/plain;
    }
}
NGINX_EOF
sed -i "s/_DOMAIN_/${DOMAIN}/g" /tmp/pygbsentry-http-only.conf

# 找到nginx配置目录
if [ -d "${NGINX_AVAILABLE_DIR}" ]; then
    cp /tmp/pygbsentry-http-only.conf "${NGINX_AVAILABLE_DIR}/${DOMAIN}-http.conf"
    ln -sf "${NGINX_AVAILABLE_DIR}/${DOMAIN}-http.conf" "${NGINX_ENABLED_DIR}/${DOMAIN}-http.conf"
elif [ -d "${NGINX_CONF_DIR}" ]; then
    cp /tmp/pygbsentry-http-only.conf "${NGINX_CONF_DIR}/${DOMAIN}-http.conf"
else
    echo "找不到nginx配置目录，请手动放置配置文件"
    exit 1
fi

nginx -t && systemctl reload nginx

# 4. 申请证书
echo "[4/5] 申请 Let's Encrypt 证书..."
certbot certonly \
    --webroot \
    --webroot-path="${WEBROOT}" \
    --email="${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}" \
    --non-interactive

echo "证书已签发: /etc/letsencrypt/live/${DOMAIN}/"

# 5. 提示后续步骤
echo "[5/5] 配置完成！"
echo ""
echo "=== 后续步骤 ==="
echo ""
echo "1. 替换 nginx 配置为完整 HTTPS 版本（见 frontend/nginx.conf）"
echo ""
echo "2. 设置证书自动续期 cron："
echo "   echo '0 0 * * * certbot renew --quiet --deploy-hook \"systemctl reload nginx\"' | crontab -"
echo ""
echo "3. 重启 PyGBSentry 后端服务"
echo ""
echo "4. 验证 HTTPS："
echo "   curl -I https://${DOMAIN}/"
echo ""
echo "5. 验证 WebRTC：在浏览器中打开 https://${DOMAIN}/ 并尝试实时预览"
