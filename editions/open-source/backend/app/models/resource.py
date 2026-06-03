from sqlalchemy import Column, String, Integer, Float, ForeignKey, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class Resource(Base):
    __tablename__ = "resources"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    # directory 节点在“选2：完全不依赖设备”模式下允许不落到任何 Asset 上。
    # channel 节点仍然会携带 asset_id，用于关联设备与鉴权/设备信息展示。
    asset_id = Column(String(32), ForeignKey("assets.id"), nullable=True, index=True)

    gb_id = Column(String(20), index=True, comment="通道国标ID")
    name = Column(String(255), comment="通道名称")

    # Type: 1=Camera, 2=Alarm, 3=Audio
    type = Column(Integer, default=1)

    # State
    status = Column(Integer, default=1, comment="1: ON, 0: OFF")
    has_audio = Column(Boolean, default=True, comment="通道是否含音频，用于播放与对讲")

    # GIS
    longitude = Column(Float)
    latitude = Column(Float)

    # Capabilities (PTZ support, resolution, etc.)
    capabilities = Column(JSON, default={})

    parent_id = Column(String(32), ForeignKey("resources.id"), nullable=True)
    # 业务分组树挂载父节点（根/目录国标 ID）；与行政区划挂载互相独立
    parent_gb_id = Column(String(20), index=True)
    # 行政区划树挂载父节点（region:xxxxxx、region:root 或行政区下目录的 gb_id）
    region_parent_gb_id = Column(String(64), index=True)
    civil_code = Column(String(16), index=True)
    node_type = Column(String(16), default="channel", index=True)
    numeric_channel_id = Column(Integer, index=True, nullable=True, comment="numeric channel ID for fast lookup")

    # GB28181 Extended Info
    address = Column(String(255), comment="安装地址")
    parental = Column(Integer, default=0, comment="是否有子设备: 0-无, 1-有")
    safety_way = Column(Integer, default=0, comment="安全模式")
    register_way = Column(Integer, default=1, comment="注册方式")
    secrecy = Column(Integer, default=0, comment="保密属性: 0-不涉密, 1-涉密")
    ip_address = Column(String(64), comment="通道IP")
    port = Column(Integer, comment="通道端口")
    password = Column(String(64), comment="通道密码")
    ptz_type = Column(Integer, default=0, comment="PTZ类型: 0-未知, 1-球机, 2-半球, 3-固定枪机, 4-遥控枪机")
    position_type = Column(Integer, default=0, comment="安装位置: 0-未知, 1-室内, 2-室外")
    room_type = Column(Integer, default=0, comment="房间类型")
    use_type = Column(Integer, default=0, comment="用途类型")
    supply_light_type = Column(Integer, default=0, comment="补光类型")
    direction_type = Column(Integer, default=0, comment="摄像机方向")
    resolution = Column(String(32), comment="分辨率")
    business_group_id = Column(String(64), comment="业务组ID")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
