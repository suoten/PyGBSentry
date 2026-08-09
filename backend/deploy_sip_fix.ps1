# =============================================================================
# GB28181 通道同步修复 - 部署脚本
# 修复内容：
#   1. P0: ZLM 故障不再触发 readiness 503（解除崩溃重启死循环）
#   2. P0: Request-URI host 改用接收方实际地址 addr[0]:addr[1]（非行政区划码）
#      根因：Request-URI 是路由地址，EasyGBS 校验 host 不匹配自己返回 400
#      From/To URI host 保持 settings.SIP_DOMAIN（身份标识，符合 GB28181 §9.2.1）
#   3. 涉及 11 个 SIP 模块文件，共 66 处 req.uri 修复
# =============================================================================
# 使用方法：在本地 PowerShell 中运行： .\deploy_sip_fix.ps1
# =============================================================================

$SSH_USER = "root"
$SSH_HOST = "pygbsentry.jjtt.net"
$REMOTE_BASE = "/www/wwwroot/pygbsentry.jjtt.net/backend"

# 需要部署的文件列表（相对于 backend/）
$FILES = @(
    "app/core/config.py",
    "app/services/health_service.py",
    "app/sip/commander.py",
    "app/sip/handlers.py",
    "app/sip/catalog.py",
    "app/sip/cascade.py",
    "app/sip/broadcast.py",
    "app/sip/device_control.py",
    "app/sip/invite.py",
    "app/sip/ptz.py",
    "app/sip/record.py",
    "app/sip/playback_control.py",
    "app/sip/subscribe_manager.py",
    "app/sip/talk.py",
    "app/services/platform_service.py",
    "app/core/xml_utils.py",
    "app/api/v1/endpoints/devices/devices_control.py"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " GB28181 通道同步修复部署" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "服务器: $SSH_USER@$SSH_HOST" -ForegroundColor Yellow
Write-Host "远程路径: $REMOTE_BASE" -ForegroundColor Yellow
Write-Host "待部署文件数: $($FILES.Count)" -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "确认部署？(y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "已取消" -ForegroundColor Red
    exit 0
}

# 上传文件
foreach ($file in $FILES) {
    $remotePath = "${SSH_USER}@${SSH_HOST}:${REMOTE_BASE}/${file}"
    Write-Host "[上传] $file ..." -NoNewline
    scp -o StrictHostKeyChecking=no $file $remotePath 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " FAILED" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 清理缓存并重启服务" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 远程命令：用单引号 here-string 避免 PowerShell 变量展开
$remoteScript = @'
cd /www/wwwroot/pygbsentry.jjtt.net/backend
echo '[1/5] 清理 __pycache__ ...'
find app -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
find app -name '*.pyc' -delete 2>/dev/null
echo '      done'

echo '[2/5] 验证 commander.py Request-URI 修复 ...'
grep -c 'req.uri.*SIP_DOMAIN' app/sip/commander.py
echo '（应为 0，表示无 SIP_DOMAIN 残留）'

echo '[3/5] 重启后端服务...'
if command -v supervisorctl &>/dev/null; then
    supervisorctl restart pygbsentry 2>/dev/null || supervisorctl restart all 2>/dev/null
    echo '      (via supervisorctl)'
elif systemctl list-units --type=service 2>/dev/null | grep -q pygbsentry; then
    systemctl restart pygbsentry
    echo '      (via systemctl)'
else
    PID=$(pgrep -f 'uvicorn.*app.main')
    if [ -n "$PID" ]; then
        echo "      找到 uvicorn PID=$PID，正在重启..."
        kill -HUP $PID 2>/dev/null || kill $PID
        echo '      (kill -HUP)'
    else
        echo '      [警告] 未找到服务，请手动重启'
    fi
fi

echo '[4/5] 等待服务启动...'
sleep 3

echo '[5/5] 查找 MediaServer 二进制...'
ZLM_PATH="/www/wwwroot/pygbsentry.jjtt.net/backend/binaries/linux64/MediaServer"
if [ -f "$ZLM_PATH" ]; then
    echo "MediaServer 已存在: OK"
else
    echo "MediaServer 缺失！全盘查找备份..."
    FOUND=$(find / -name "MediaServer" -type f 2>/dev/null | head -5)
    if [ -n "$FOUND" ]; then
        echo "找到备份:"
        echo "$FOUND"
        FIRST=$(echo "$FOUND" | head -1)
        mkdir -p "$(dirname "$ZLM_PATH")"
        cp "$FIRST" "$ZLM_PATH"
        chmod +x "$ZLM_PATH"
        echo "恢复完成！"
    else
        echo "未找到备份。恢复方案："
        echo "  方案A: echo 'EMBEDDED_ZLM_ENABLED=false' >> /www/wwwroot/pygbsentry.jjtt.net/backend/.env"
        echo "  方案B: 手动拷贝 MediaServer 二进制到 $ZLM_PATH"
    fi
fi

echo ''
echo '========================================'
echo ' 验证'
echo '========================================'
echo -n 'readiness 状态码: '
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health/ready
echo ''
echo '（期望 200，不再是 503）'
'@

ssh -o StrictHostKeyChecking=no ${SSH_USER}@${SSH_HOST} $remoteScript

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " 部署完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "验证后端是否启动：" -ForegroundColor Yellow
Write-Host "  curl -s http://127.0.0.1:8000/health/ready" -ForegroundColor Yellow
Write-Host ""
Write-Host "观察 SIP 通道同步日志：" -ForegroundColor Yellow
Write-Host "  tail -f /www/wwwroot/pygbsentry.jjtt.net/backend/logs/app.log | grep CATALOG" -ForegroundColor Yellow
