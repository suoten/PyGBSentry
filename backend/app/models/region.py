import uuid
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class Region(Base):
    """行政区划模型。

    内置行政区划数据（来源：民政部行政区划代码），通过
    ``scripts/seed_regions.py`` 导入。``code`` 为行政区划编码（唯一），
    ``parent_id`` 自引用形成省/市/区县层级。``level``: 0=国家, 1=省, 2=市, 3=区县。
    与 ``Resource.civil_code`` 配合实现通道按行政区域检索。
    """

    __tablename__ = "regions"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    parent_id = Column(String(32), nullable=True, index=True)
    level = Column(Integer, default=0)
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now())
