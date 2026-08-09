#!/bin/bash
# SIP 注册诊断 - 实时查看下级平台 36.34.0.68 的注册情况
# 用法: bash scripts/diag_sip_register.sh

LOG_DIR="/www/wwwroot/pygbsentry.jjtt.net/backend/logs"

echo "=" * 60
echo "SIP 注册诊断 - 监控 36.34.0.68"
echo "=" * 60
echo ""
echo "1. 检查 IP 黑名单..."
cd /www/wwwroot/pygbsentry.jjtt.net/backend
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from app.db.session import AsyncSessionLocal
from sqlalchemy import text
async def main():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text('SELECT ip, reason, created_at FROM ip_blacklist'))
        rows = r.fetchall()
        if not rows:
            print('   黑名单为空')
        else:
            for row in rows:
                print(f'   {row[0]} | reason={row[1]} | time={row[2]}')
asyncio.run(main())
"

echo ""
echo "2. 检查 ParentPlatform 配置..."
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from app.db.session import AsyncSessionLocal
from sqlalchemy import text
async def main():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text('SELECT server_gb_id, server_ip, server_port, name, enable, is_online, password FROM parent_platforms'))
        rows = r.fetchall()
        if not rows:
            print('   parent_platforms 表为空 - 下级平台未配置！')
            print('   → 需要在管理后台添加下级平台')
        else:
            for row in rows:
                pwd_status = '有密码' if row[6] else '无密码'
                print(f'   GB_ID={row[0]} | IP={row[1]}:{row[2]} | name={row[3]} | enable={row[4]} | online={row[5]} | {pwd_status}')
asyncio.run(main())
"

echo ""
echo "3. 实时监控 SIP 日志（Ctrl+C 停止）..."
echo "    只显示 36.34.0.68 和 REGISTER 相关日志"
echo ""
tail -f "$LOG_DIR/app.log" | grep --line-buffered -E "36\.34\.0\.68|REGISTER|register|Forbidden|Auth|401|challenge|digest|_auth_diag|candidate|_pf_pw|_pf2_pw|_asset_pw"
