from sqlalchemy import Column, String, Integer, Boolean, Float, DateTime, Text
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class MediaNode(Base):
    __tablename__ = "media_nodes"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    ip = Column(String(64), nullable=False)
    public_ip = Column(String(64), comment="公网IP")
    # 对外播放/推流访问地址（优先使用该字段；为空时回退 public_ip/ip）
    stream_ip = Column(String(128), nullable=True, comment="流媒体对外访问地址（IP或域名）")
    # Hook 回调在节点侧可用的后端地址（用于 NAT/容器场景），为空则使用默认推导
    hook_base_url = Column(String(255), nullable=True, comment="ZLM Hook Base URL（可选覆盖）")
    hook_ip = Column(String(64), nullable=True, comment="Hook 回调连通用 IP（可选）")
    sdp_ip = Column(String(64), nullable=True, comment="SDP 对外 IP（NAT 场景可选）")

    http_port = Column(Integer, default=80)
    https_port = Column(Integer, default=0, comment="HTTPS 端口（可选）")
    rtsp_port = Column(Integer, default=554)
    rtsps_port = Column(Integer, default=0, comment="RTSPS 端口（可选）")
    rtmp_port = Column(Integer, default=1935)
    rtmps_port = Column(Integer, default=0, comment="RTMPS 端口（可选）")
    rtp_proxy_port = Column(Integer, default=10000)
    # 收流端口模式：single|range
    rtp_port_mode = Column(String(16), default="single", comment="收流端口模式：single|range")
    rtp_port_range_start = Column(Integer, default=0, comment="收流端口范围起始（range 模式）")
    rtp_port_range_end = Column(Integer, default=0, comment="收流端口范围结束（range 模式）")
    record_mgr_port = Column(Integer, default=0, comment="录像管理服务端口（可选）")
    record_file_second = Column(Integer, default=0, comment="录像分片时长秒（0=使用全局默认）")
    record_sample_ms = Column(Integer, default=0, comment="录像采样间隔毫秒（0=使用全局默认）")
    protocol_mp4_max_second = Column(Integer, default=0, comment="MP4单文件最大时长秒（0=使用全局默认）")

    secret = Column(String(64), nullable=False)

    # 内置 ZLMediaKit 启动时写入磁盘并传 -s；外置节点仅作备份/迁移，不由本进程加载
    zlm_ssl_merged_pem = Column(Text, nullable=True, comment="ZLM HTTPS 合并 PEM（私钥+证书链，见官方文档）")

    is_online = Column(Boolean, default=False)
    load = Column(Float, default=0.0)
    last_seen_at = Column(DateTime, nullable=True, comment="最后一次收到 hook/keepalive 的时间")
    last_probe_error = Column(String(512), nullable=True, comment="最近一次主动探测错误（可选）")

    is_embedded = Column(Boolean, default=False, comment="是否为内置节点")
    auto_config_enabled = Column(Boolean, default=False, comment="是否自动配置媒体服务（内置 ZLM）")
