"""encrypt password fields (assets/resources/parent_platforms/access_sources)

P-SEC: 修复设备/平台密码明文存储漏洞。Asset / Resource / ParentPlatform / AccessSource
的 password 列此前以明文落库，数据库泄露即暴露 SIP 鉴权密码。本迁移：
1) 将 assets / resources / parent_platforms 的 password 列扩宽到 VARCHAR(255)
   （AES-256-GCM 密文 base64 长度大于原 64/128 明文长度，否则 PostgreSQL 会因超长
   截断/报错导致解密失败）；access_sources 已为 255，无需扩宽。
2) 对四张表中已存在的明文 password 执行一次性 AES-256-GCM 加密迁移。

幂等性：通过 decrypt_field 探测——能解密则视为已加密跳过，解密失败（返回 None）
才视为明文予以加密。重复执行不会二次加密。兼容 SQLite / PostgreSQL / MySQL。
密钥来自 settings.FIELD_ENCRYPTION_KEY（缺失则 encrypt_field 抛 ValueError，迁移
fail-loud，防止用空密钥迁移出无法解密的密文）。

注：本迁移为数据迁移，仅支持 online 模式（需 Python 运行 decrypt/encrypt），
不支持 `alembic upgrade --sql` 离线模式。

Revision ID: c1d2e3f4a5b6
Revises: a2b3c4d5e6f7, b1c2d3e4f5g6
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
# Merge node: a2b3c4d5e6f7 与 b1c2d3e4f5g6 此前均以 f1a2b3c4d5e6 为父，形成双头，
# 导致 `alembic upgrade head` 报 multiple heads 错误。此处合并以线性化迁移树，
# 使本迁移成为单一新 head。
down_revision: Union[str, Sequence[str], None] = ('a2b3c4d5e6f7', 'b1c2d3e4f5g6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 统一 purpose=sip_password，与 field_crypto 及模型 decrypted_password 保持一致。
_PASSWORD_TABLES = (
    "assets",
    "resources",
    "parent_platforms",
    "access_sources",
)

# password 列需要扩宽的表（access_sources 建表时已为 VARCHAR(255)，无需处理）。
_WIDEN_TABLES = ("assets", "resources", "parent_platforms")


def _widen_password_columns(dialect: str) -> None:
    """将 password 列扩宽到 VARCHAR(255)。

    PostgreSQL 强制 VARCHAR 长度（超长报错），MySQL 同理；SQLite 不强制长度，
    且 ALTER 列需重建表（batch 代价高），故跳过。
    """
    if dialect.startswith("post"):
        for t in _WIDEN_TABLES:
            op.execute(f"ALTER TABLE {t} ALTER COLUMN password TYPE VARCHAR(255)")
    elif dialect == "mysql":
        # MySQL MODIFY 需重述列定义；这些列在模型中均为 nullable，保持 NULL 语义。
        for t in _WIDEN_TABLES:
            op.execute(f"ALTER TABLE {t} MODIFY COLUMN password VARCHAR(255) NULL")
    # SQLite: VARCHAR 长度不强制约束，跳过


def _encrypt_existing_passwords() -> None:
    """对四张表的明文 password 执行一次性加密迁移（幂等）。"""
    bind = op.get_bind()
    if bind is None:
        # offline (--sql) 模式无 bind，数据迁移无法执行
        print("[c1d2e3f4a5b6] offline mode: skipping data encryption (run in online mode)")
        return

    from app.core.field_crypto import encrypt_field, decrypt_field

    purpose = "sip_password"
    migrated = 0
    skipped = 0
    for table in _PASSWORD_TABLES:
        rows = bind.execute(
            sa.text(f"SELECT id, password FROM {table} WHERE password IS NOT NULL AND password <> ''")
        ).fetchall()
        for rid, pwd in rows:
            # 幂等探测：能解密 => 已是密文，跳过；解密失败 => 视为明文予以加密。
            # 纯明文几乎不可能误判为可解密（AES-256-GCM tag 校验）。
            if decrypt_field(pwd, purpose=purpose) is not None:
                skipped += 1
                continue
            encrypted = encrypt_field(pwd, purpose=purpose)
            bind.execute(
                sa.text(f"UPDATE {table} SET password = :pw WHERE id = :rid"),
                {"pw": encrypted, "rid": rid},
            )
            migrated += 1

    print(
        f"[c1d2e3f4a5b6] password encryption migration: "
        f"{migrated} row(s) encrypted, {skipped} already-encrypted row(s) skipped."
    )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = (getattr(getattr(bind, "dialect", None), "name", "") or "").lower() if bind else ""
    _widen_password_columns(dialect)
    _encrypt_existing_passwords()


def downgrade() -> None:
    """降级仅回滚列宽；不将密文解密回明文（解密回明文属安全倒退，无可靠逆操作）。"""
    bind = op.get_bind()
    dialect = (getattr(getattr(bind, "dialect", None), "name", "") or "").lower() if bind else ""
    narrow = {
        "assets": "VARCHAR(64)",
        "resources": "VARCHAR(64)",
        "parent_platforms": "VARCHAR(128)",
    }
    if dialect.startswith("post"):
        for t, ty in narrow.items():
            op.execute(f"ALTER TABLE {t} ALTER COLUMN password TYPE {ty}")
    elif dialect == "mysql":
        for t, ty in narrow.items():
            op.execute(f"ALTER TABLE {t} MODIFY COLUMN password {ty} NULL")
    # SQLite: 跳过（不强制长度）
