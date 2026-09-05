import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.db.base import Base
from app.core.field_crypto import encrypt_field, decrypt_field

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class Resource(Base):
    """资源/通道模型（GB28181 通道目录）。

    一个 ``Asset`` 可包含多个 ``Resource``（通道）。``asset_id`` 允许为 NULL，
    以支持「目录节点」（无物理设备的逻辑分组节点，见 schema_upgrade 迁移说明）。
    ``node_type`` 区分通道与目录节点：channel / directory。
    """

    __tablename__ = "resources"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    # asset_id 允许为 NULL：目录节点不依赖物理设备
    asset_id = Column(String(32), ForeignKey("assets.id"), nullable=True, index=True)

    gb_id = Column(String(20), index=True, comment="通道国标ID")
    name = Column(String(255), comment="通道名称")

    # Type: 1=Camera, 2=Alarm, 3=Audio
    type = Column(Integer, default=1)

    # State: 1=ON, 0=OFF
    status = Column(Integer, default=1, index=True)

    # GIS
    longitude = Column(Float)
    latitude = Column(Float)

    # Capabilities (PTZ support, resolution, etc.)
    capabilities = Column(JSON, default=dict)

    # 目录树结构
    parent_id = Column(String(32), ForeignKey("resources.id"), nullable=True)
    parent_gb_id = Column(String(20), nullable=True, index=True)
    civil_code = Column(String(64), nullable=True, index=True, comment="行政区划编码")
    node_type = Column(String(32), default="channel", index=True)
    region_parent_gb_id = Column(String(64), nullable=True, index=True)

    # GB28181 Extended Fields
    address = Column(String(255), nullable=True)
    parental = Column(Integer, default=0)
    safety_way = Column(Integer, default=0)
    register_way = Column(Integer, default=1)
    secrecy = Column(Integer, default=0)
    ip_address = Column(String(64), nullable=True)
    port = Column(Integer, nullable=True)
    password = Column(String(255), nullable=True, comment="通道密码（AES-256-GCM 密文，base64 编码）")

    @property
    def decrypted_password(self) -> str | None:
        """解密后的明文密码，供 SIP Digest 计算等需要明文的场景使用。

        ``password`` 列始终为密文；本属性读取时解密、赋值时加密，实现对调用方
        透明的字段级加解密。解密失败返回 None（fail-closed）。
        """
        if not self.password:
            return None
        return decrypt_field(self.password, purpose="sip_password")

    @decrypted_password.setter
    def decrypted_password(self, plaintext: str | None) -> None:
        """赋值明文密码时自动加密后写入 ``password`` 列。"""
        if not plaintext:
            self.password = None
            return
        self.password = encrypt_field(plaintext, purpose="sip_password")
    ptz_type = Column(Integer, default=0)
    position_type = Column(Integer, default=0)
    room_type = Column(Integer, default=0)
    use_type = Column(Integer, default=0)
    supply_light_type = Column(Integer, default=0)
    direction_type = Column(Integer, default=0)
    resolution = Column(String(32), nullable=True)
    business_group_id = Column(String(64), nullable=True)
    has_audio = Column(Boolean, default=True)
    # 预计算的 SHA256 整数，用于通道快速查找
    numeric_channel_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), index=True)
