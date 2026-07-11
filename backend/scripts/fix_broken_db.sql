-- ============================================================================
-- PyGBSentry 数据库修复脚本
-- 用途：修复因迁移缺失导致的 users 表列缺失 + alembic 版本损坏
-- 适用：PostgreSQL（服务器 /www/wwwroot/pygbsentry.jjtt.net/backend）
-- 日期：2026-07-11
-- ============================================================================
--
-- 使用方法：
--   方式1（psql 命令行）：
--     psql -U postgres -d pygb28181 -f scripts/fix_broken_db.sql
--
--   方式2（宝塔 phpMyAdmin）：
--     登录 phpMyAdmin → 选择 pygb28181 数据库 → SQL → 粘贴执行
--
--   方式3（Python）：
--     cd /www/wwwroot/pygbsentry.jjtt.net/backend
--     python -c "
--     import asyncio, asyncpg
--     async def main():
--         conn = await asyncpg.connect('postgresql://postgres:YOUR_PASSWORD@localhost:5432/pygb28181')
--         await conn.execute(open('scripts/fix_broken_db.sql').read())
--         await conn.close()
--     asyncio.run(main())
--     "
-- ============================================================================

-- 1. 添加 users 表缺失的 5 个列（IF NOT EXISTS 保证幂等）
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_domain VARCHAR(16) DEFAULT 'tenant';
ALTER TABLE users ADD COLUMN IF NOT EXISTS site_role VARCHAR(32) DEFAULT 'normal';
ALTER TABLE users ADD COLUMN IF NOT EXISTS agreed_tos_version VARCHAR(32);
ALTER TABLE users ADD COLUMN IF NOT EXISTS agreed_privacy_version VARCHAR(32);
ALTER TABLE users ADD COLUMN IF NOT EXISTS agreed_dev_version VARCHAR(32);

-- 2. 创建索引（IF NOT EXISTS 保证幂等）
CREATE INDEX IF NOT EXISTS ix_users_auth_domain ON users (auth_domain);
CREATE INDEX IF NOT EXISTS ix_users_site_role ON users (site_role);

-- 3. 修复 operation_audits.tenant_id（如果缺失）
ALTER TABLE operation_audits ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(36);

-- 4. 修复 alembic 版本号 — 标记为最新 head
--    当前 head = k3c4d5e6f7g8（最新迁移）
UPDATE alembic_version SET version_num = 'k3c4d5e6f7g8';

-- 5. 验证修复结果
SELECT '=== users 表列 ===' AS info;
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'users' AND column_name IN
    ('auth_domain', 'site_role', 'agreed_tos_version', 'agreed_privacy_version', 'agreed_dev_version')
ORDER BY column_name;

SELECT '=== alembic 版本 ===' AS info;
SELECT * FROM alembic_version;

SELECT '=== 修复完成 ===' AS info;
