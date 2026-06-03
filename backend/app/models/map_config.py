from sqlalchemy import Column, String, Integer, Float, Boolean
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class MapConfig(Base):
    __tablename__ = "map_config"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    name = Column(String(64), default="默认地图")

    # Provider: tianditu, baidu, gaode, tencent, osm, vector
    provider = Column(String(32), default="tianditu")

    # API Key / Token
    api_key = Column(String(128))

    # Vector Tile specific
    vector_tile_url = Column(String(512), nullable=True, comment="MVT Vector Tile URL Template")

    # Center Point
    center_lng = Column(Float, default=116.404)
    center_lat = Column(Float, default=39.915)
    zoom_level = Column(Integer, default=12)
    min_zoom = Column(Integer, default=1)
    max_zoom = Column(Integer, default=20)

    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
