import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4


def generate_uuid():
    return _uuid7_impl().hex


class Mp4VodChannel(Base):
    """本地 MP4 虚拟通道(ROADMAP Phase3:wvp #2257 类需求)。

    用户上传 MP4 文件到服务器本地盘(``VOD_MP4_DIR``),通过 ZLM ``loadMP4File``
    以直播协议循环点播;不计入 GB28181 通道配额。文件名只存服务端生成的相对名
    (不含用户输入,防路径穿越);播放要求所选 ZLM 节点本地可读该目录
    (单机/内嵌部署天然满足,多节点需共享存储)。
    """

    __tablename__ = "mp4_vod_channels"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    name = Column(String(128), nullable=False, comment="展示名(默认取上传文件名去扩展名)")
    original_name = Column(String(255), nullable=True, comment="原始文件名(仅展示)")
    # 服务端生成的相对文件名(如 t1/ab12cd34.mp4),不含用户输入,防穿越
    file_name = Column(String(128), nullable=False, unique=True)
    file_size = Column(BigInteger, nullable=False, default=0)
    enabled = Column(Boolean, default=True, index=True)

    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=func.now())
