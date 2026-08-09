"""encrypt media_node secret field

P0-02: 修复媒体节点密钥明文存储漏洞。``media_nodes.secret`` 列此前以明文落库，
该密钥用于控制 ZLMediaKit 媒体服务器，泄露后可被完全控制。本迁移：
1) 将 media_nodes.secret 列从 VARCHAR(64) 扩宽到 VARCHAR(255)
   （AES-256-GCM 密文 base64 长度大于原 64 明文长度，否则 PostgreSQL 会因超长
   截断/报错导致解密失败）。
2) 对已存在的明文 secret 执行一次性 AES-256-GCM 加密迁移。

幂等性：通过 decrypt_field 探测——能解密则视为已加密跳过，解密失败（返回 None）
才视为明文予以加密。重复执行不会二次加密。兼容 SQLite / PostgreSQL / MySQL。
密钥来自 settings.FIELD_ENCRYPTION_KEY（缺失则 encrypt_field 抛 ValueError，迁移
fail-loud，防止用空密钥迁移出无法解密的密文）。

purpose="media_secret" 与 sip_password 隔离派生密钥，避免跨字段密钥复用。

注：本迁移为数据迁移，仅支持 online 模式（需 Python 运行 decrypt/encrypt），
不支持 `alembic upgrade --sql` 离线模式。

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _widen_secret_column(dialect: str) -> None:
    """将 media_nodes.secret 列从 VARCHAR(64) 扩宽到 VARCHAR(255)。

    PostgreSQL 强制 VARCHAR 长度（超长报错），MySQL 同理；SQLite 不强制长度，
    且 ALTER 列需重建表（batch 代价高），故跳过。
    """
    if dialect.startswith("post"):
        op.execute("ALTER TABLE media_nodes ALTER COLUMN secret TYPE VARCHAR(255)")
    elif dialect == "mysql":
        # MySQL MODIFY 需重述列定义；secret 列为 NOT NULL，保持语义。
        op.execute("ALTER TABLE media_nodes MODIFY COLUMN secret VARCHAR(255) NOT NULL")
    # SQLite: VARCHAR 长度不强制约束，跳过


def _encrypt_existing_secrets() -> None:
    """对 media_nodes 表的明文 secret 执行一次性加密迁移（幂等）。"""
    bind = op.get_bind()
    if bind is None:
        # offline (--sql) 模式无 bind，数据迁移无法执行
        print("[d1e2f3a4b5c6] offline mode: skipping data encryption (run in online mode)")
        return

    from app.core.field_crypto import encrypt_field, decrypt_field

    purpose = "media_secret"
    migrated = 0
    skipped = 0
    rows = bind.execute(
        sa.text("SELECT id, secret FROM media_nodes WHERE secret IS NOT NULL AND secret <> ''")
    ).fetchall()
    for rid, sec in rows:
        # 幂等探测：能解密 => 已是密文，跳过；解密失败 => 视为明文予以加密。
        # 纯明文几乎不可能误判为可解密（AES-256-GCM tag 校验）。
        # FIX [2026-07-19]: 必须使用 allow_plaintext=False 严格模式——
        # 默认 True 时明文会返回原值（非 None），导致明文被误判为已加密而跳过迁移。
        if decrypt_field(sec, purpose=purpose, allow_plaintext=False) is not None:
            skipped += 1
            continue
        encrypted = encrypt_field(sec, purpose=purpose)
        bind.execute(
            sa.text("UPDATE media_nodes SET secret = :sec WHERE id = :rid"),
            {"sec": encrypted, "rid": rid},
        )
        migrated += 1

    print(
        f"[d1e2f3a4b5c6] media_node secret encryption migration: "
        f"{migrated} row(s) encrypted, {skipped} already-encrypted row(s) skipped."
    )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = (getattr(getattr(bind, "dialect", None), "name", "") or "").lower() if bind else ""
    _widen_secret_column(dialect)
    _encrypt_existing_secrets()


def downgrade() -> None:
    """降级仅回滚列宽；不将密文解密回明文（解密回明文属安全倒退，无可靠逆操作）。"""
    bind = op.get_bind()
    dialect = (getattr(getattr(bind, "dialect", None), "name", "") or "").lower() if bind else ""
    if dialect.startswith("post"):
        op.execute("ALTER TABLE media_nodes ALTER COLUMN secret TYPE VARCHAR(64)")
    elif dialect == "mysql":
        op.execute("ALTER TABLE media_nodes MODIFY COLUMN secret VARCHAR(64) NOT NULL")
    # SQLite: 跳过（不强制长度）
