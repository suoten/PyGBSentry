import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class ConfigRevision(Base):
    """配置中心发布版本。

    每次发布生成一条不可变记录（``status=published``），``revision`` 单调递增。
    ``content`` 为 JSON，包含所有模块的配置快照。插件启动时通过
    ``config_center_service._load_published_modules`` 读取最新已发布版本，
    合并到各插件的 ``config_template``。
    """

    __tablename__ = "config_revisions"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    revision = Column(Integer, nullable=False, index=True)
    status = Column(String(24), nullable=False, default="published")

    content = Column(Text, nullable=False, default="{}")
    created_by = Column(String(64), nullable=False, default="system")

    created_at = Column(DateTime, default=func.now())
