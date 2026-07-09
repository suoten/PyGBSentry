import uuid
from sqlalchemy import Column, String, Integer, Boolean, Float, DateTime, Text
from app.db.base import Base
from app.core.field_crypto import encrypt_field, decrypt_field

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class MediaNode(Base):
    """媒体节点模型（ZLMediaKit 实例）。

    一个部署可包含多个媒体节点（内置节点 ``is_embedded=True``，外部节点=False）。
    ``secret`` 必须与 ZLMediaKit 的 ``api.secret`` 一致，否则 API 调用会被拒绝。
    启动时会校验 ``settings.MEDIA_SERVER_SECRET`` 与内置节点的 ``secret`` 一致性。
    """

    __tablename__ = "media_nodes"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    ip = Column(String(64), nullable=False, index=True)
    public_ip = Column(String(64), comment="公网IP")
    stream_ip = Column(String(128), nullable=True, comment="流媒体收发IP（可与信令IP分离）")
    hook_base_url = Column(String(255), nullable=True)
    hook_ip = Column(String(64), nullable=True)
    sdp_ip = Column(String(64), nullable=True)

    http_port = Column(Integer, default=80)
    https_port = Column(Integer, default=0)
    rtsp_port = Column(Integer, default=554)
    rtsps_port = Column(Integer, default=0)
    rtmp_port = Column(Integer, default=1935)
    rtmps_port = Column(Integer, default=0)
    rtp_proxy_port = Column(Integer, default=10000)

    # RTP 端口分配策略：single（单端口复用）或 range（端口范围）
    rtp_port_mode = Column(String(16), default="single")
    rtp_port_range_start = Column(Integer, default=0)
    rtp_port_range_end = Column(Integer, default=0)

    # 录像相关
    record_mgr_port = Column(Integer, default=0)
    record_file_second = Column(Integer, default=0)
    record_sample_ms = Column(Integer, default=0)
    protocol_mp4_max_second = Column(Integer, default=0)

    # secret 列存储 AES-256-GCM 密文（base64），禁止明文落库
    secret = Column(String(255), nullable=False, comment="ZLM API 密钥（AES-256-GCM 密文，base64 编码）")

    @property
    def decrypted_secret(self) -> str | None:
        """解密后的明文密钥，供 ZLM API 调用、启动一致性校验等需要明文的场景使用。

        ``secret`` 列始终为密文；本属性读取时解密、赋值时加密，实现对调用方
        透明的字段级加解密。解密失败（密钥变更/数据损坏）返回 None，遵循
        fail-closed 原则，避免将密文误当作明文参与 ZLM API 鉴权。
        """
        if not self.secret:
            return None
        return decrypt_field(self.secret, purpose="media_secret")

    @decrypted_secret.setter
    def decrypted_secret(self, plaintext: str | None) -> None:
        """赋值明文密钥时自动加密后写入 ``secret`` 列。"""
        if not plaintext:
            self.secret = None
            return
        self.secret = encrypt_field(plaintext, purpose="media_secret")
    zlm_ssl_merged_pem = Column(Text, nullable=True)

    is_online = Column(Boolean, default=False)
    load = Column(Float, default=0.0)
    last_seen_at = Column(DateTime, nullable=True)
    last_probe_error = Column(String(512), nullable=True)

    is_embedded = Column(Boolean, default=False, comment="是否为内置节点")
    auto_config_enabled = Column(Boolean, default=False)
