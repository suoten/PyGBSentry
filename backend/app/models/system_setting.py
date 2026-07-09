import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class SystemSetting(Base):
    """系统配置键值对（通用配置存储）。

    存储非结构化的全局配置（如流模式学习状态、bootstrap 配置等），
    与配置中心（``config_center_service``）的 ``ConfigRevision`` 互补：
    本表用于运行时可变的轻量配置，配置中心用于版本化发布的大型模块配置。
    """

    __tablename__ = "system_settings"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    setting_key = Column(String(128), unique=True, nullable=False, index=True)
    setting_value = Column(String(2000), nullable=False)

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
