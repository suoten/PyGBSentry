# -------------------------------------------------------------------------
# 🚀 Project: PyGBSentry
# ✍️ Author: suoten
# 📧 Email: suoten@163.com
# 📄 License: AGPL-3.0-or-later WITH Classpath-Exception
# -------------------------------------------------------------------------

import os
import logging
from pathlib import Path
from typing import List, Optional, Union
import secrets as _secrets
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, PostgresDsn, field_validator, ValidationInfo, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 先把 .env 写入 os.environ，否则仅靠 pydantic 读 .env 时 os.getenv 仍为 None（如 ZLM 生产编译门控）
_backend_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(_backend_dir / ".env", override=False)


class Settings(BaseSettings):
    PROJECT_NAME: str = "PyGBSentry"
    PROJECT_VERSION: str = os.environ.get("BUILD_VERSION", "1.1.0")  # 版本号支持构建时注入(BUILD_VERSION)，回退为硬编码值；变更时需同步更新
    PROJECT_LICENSE: str = "AGPL-3.0-or-later"
    PROJECT_LICENSE_URL: str = "https://www.gnu.org/licenses/agpl-3.0.html"
    PLUGIN_LICENSE_EXCEPTION: str = "classpath"
    API_V1_STR: str = "/api/v1"
    APP_ENV: str = "dev"  # 默认开发模式；生产部署必须在 .env 中显式设置 APP_ENV=prod
    APP_LANGUAGE: str = "zh"  # 错误消息语言 (zh/en)，影响后端 i18n 模块输出
    APP_TIMEZONE: str = "Asia/Shanghai"
    # P1-fix [2026-07-17]: APP_TIMEZONE_OFFSET_HOURS — 数值型时区偏移（小时），用于 datetime.timezone 构造。
    # 原 platform_service.py 使用 getattr(settings, "APP_TIMEZONE_OFFSET_HOURS", 8) 动态获取违反硬约束 #41。
    # 默认 8（UTC+8 北京时间，与历史 getattr 默认值一致）。优先使用 APP_TIMEZONE（IANA 名称）做 tzinfo；
    # 此项仅用于无法用 IANA 名称的场合。
    APP_TIMEZONE_OFFSET_HOURS: float = 8.0
    LOG_DIR: str = "logs"
    LOG_FORMAT: str = "text"
    # P3-05: stderr 日志级别覆盖（空字符串=自动按 APP_ENV 推导：prod→WARNING, dev→INFO, debug→DEBUG）
    LOG_LEVEL_STDERR: str = ""

    # FIX [2026-07-22 P0]: ZLMediaKit 故障不应导致 readiness 探针失败。
    # 原行为：ZLM 二进制缺失 → mark_degraded("zlm_down") → /health/ready 返回 503 →
    # 外部进程管理器（宝塔/systemd）健康检查失败 → 强制重启 → ZLM 仍缺失 → 崩溃重启死循环。
    # ZLM 是媒体转发层，SIP 信令/设备管理/通道同步不依赖 ZLM，不应因 ZLM 故障重启整个服务。
    # 默认 False：ZLM 故障只影响视频播放，readiness 仍返回 200，SIP 业务可正常运行。
    # K8s 部署如需原行为（ZLM 故障时不导流量），显式设为 true。
    READINESS_FAIL_ON_ZLM_DOWN: bool = False

    # Security — 密钥分离，不同用途使用独立密钥
    SECRET_KEY: str = ""
    SIP_NONCE_SECRET: str = ""  # SIP nonce HMAC独立密钥
    FIELD_ENCRYPTION_KEY: str = ""  # 字段加密独立密钥
    TOTP_ENCRYPTION_KEY: str = ""  # TOTP密钥加密独立密钥，为空时从SECRET_KEY派生
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 从48小时缩短为2小时，配合refresh token使用
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Security switches
    ALLOW_PUBLIC_REGISTRATION: bool = False
    ENABLE_AUTO_DISCOVERY: bool = False  # S-06 默认关闭未知设备自动注册，防止伪造设备
    ENABLE_OPENAPI_DOCS: bool = False  # 默认关闭, dev 环境可设 True
    ENABLE_SECURITY_HEADERS: bool = True
    ENABLE_CSP: bool = True
    # CSP connect-src 额外白名单：逗号分隔的源表达式（含协议+主机+可选端口），
    # 追加到 'self' 和自动推导的流媒体公网源（STREAM_PUBLIC_SCHEME/HOST/PORT）之后。
    # 默认包含 ArcGIS 矢量瓦片（OpenLayers VectorTileSource 通过 XHR 加载 .pbf）。
    # 如使用自定义矢量瓦片服务或外置 ZLMediaKit 节点（非 STREAM_PUBLIC_HOST），请在此追加对应源。
    # 示例：CSP_CONNECT_SRC_DOMAINS=https://basemaps.arcgis.com,http://media2.example.com:80,wss://media2.example.com:80
    CSP_CONNECT_SRC_DOMAINS: str = "https://basemaps.arcgis.com"
    METRICS_ALLOWED_NETWORKS: list[str] = ["127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    # When True, use Alembic for schema migration on startup instead of schema_upgrade.py
    USE_ALEMBIC: bool = True
    ENABLE_CROSS_ORIGIN_ISOLATION: bool = False
    CROSS_ORIGIN_EMBEDDER_POLICY: str = "credentialless"
    ENABLE_SHUTDOWN_API: bool = False
    SHUTDOWN_API_LOCAL_ONLY: bool = True
    # P1-08: 生产环境强制 HTTPS — 当 APP_ENV=prod 且 FORCE_HTTPS_IN_PRODUCTION=true 时，
    # HTTP 请求自动 301 重定向到 HTTPS（检查 X-Forwarded-Proto 头）
    FORCE_HTTPS_IN_PRODUCTION: bool = True
    # True 时 require_roles 拒绝（403）写入审计中心；默认 False 避免普通浏览产生大量记录
    AUDIT_RBAC_ROLE_DENIALS: bool = False
    AUDIT_WEBHOOK_TIMEOUT: int = 5
    # P1-fix [2026-07-17]: 审计 Webhook URL，原 audit_center_service.py 使用
    # getattr(settings, "AUDIT_WEBHOOK_URL", None) 动态获取违反硬约束 #41。默认空（不推送）
    AUDIT_WEBHOOK_URL: Union[str, None] = None
    # P0-11#3: dev/test 环境显式跳过 market_builtin 占位符/完整性校验（生产环境忽略此 flag）
    _DEV_SKIP_VERIFY: bool = False

    # 自动备份配置
    AUTO_BACKUP_ENABLED: bool = False
    AUTO_BACKUP_HOUR: int = 2
    AUTO_BACKUP_RETENTION_DAYS: int = 30
    BACKUP_ENCRYPTION_ENABLED: bool = True

    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []  # 移除硬编码CORS，强制env配置
    BACKEND_PUBLIC_HOST: str = "localhost"
    BACKEND_PUBLIC_PORT: int = 8000
    # P1-fix [2026-07-17]: uvicorn 启动绑定地址 — 原 run_server.py 使用 getattr(settings, "HOST", "0.0.0.0")
    # 和 getattr(settings, "PORT", 8000) 动态获取违反硬约束 #41
    HOST: str = "0.0.0.0"  # uvicorn 绑定地址（0.0.0.0=所有网卡，127.0.0.1=仅本机）
    PORT: int = 8000  # uvicorn 监听端口

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""  # MUST be set via .env or environment variable
    POSTGRES_DB: str = "pygb28181"
    POSTGRES_PORT: int = 5432
    DATABASE_TYPE: str = "postgresql"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "pygb28181"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = ""  # MUST be set via .env or environment variable
    DATABASE_SQLITE_PATH: str = "./pygbsentry.db"
    SQLITE_BUSY_TIMEOUT_MS: int = 15000
    SQLITE_CONNECT_TIMEOUT_SECONDS: float = 15.0
    # UNIFIED: SQLite 与非 SQLite 统一使用 DB_POOL_SIZE / DB_MAX_OVERFLOW（见下方 DB Optimization 段）
    # 已移除废弃的 SQLITE_POOL_SIZE / SQLITE_MAX_OVERFLOW，避免双套配置引起混淆
    # 启动时是否执行业务/行政区 parent 字段拆分迁移（旧库升级用）。默认 False，避免阻塞启动；需迁移时改 True 或用手动脚本
    RUN_SPLIT_CATALOG_MIGRATIONS_ON_STARTUP: bool = False
    # 启动时是否从 data/region.sql 导入行政区划（行数多，旧实现每行 flush 会极慢）。默认 False；需要时在 .env 设 true 或运行 scripts/seed_regions.py
    RUN_REGION_SEED_ON_STARTUP: bool = False
    # 启动时是否执行 ensure_embedded_media_node（补全内置 ZLM 节点记录）。默认 False：initial_data 已创建时可跳过，避免 SQLite 会话层偶发卡死导致整站起不来
    ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP: bool = True  # 默认开启，启动时自动补全内置ZLM节点，与wvp对齐
    SQLALCHEMY_DATABASE_URI: Union[str, None] = None

    # DB Optimization
    # FIX: [2026-07-16 P0] 原 DB_POOL_SIZE=100 + DB_MAX_OVERFLOW=50 默认值过高，
    # 多实例部署时连接数爆炸（100+50=150/实例），PostgreSQL 默认 max_connections=100
    # 会被耗尽。降为 20+10=30/实例，可通过 .env 调整。
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800
    # P2-03: 慢查询监控阈值（秒），超过此值的查询将记录 WARNING 日志
    SLOW_QUERY_THRESHOLD_SECONDS: float = 1.0
    # P1-fix [2026-07-17]: SQLAlchemy 语句缓存大小（0=禁用，生产环境可设为100启用）
    # 原 db/session.py 使用 getattr(settings, "DB_STATEMENT_CACHE_SIZE", 0) 动态获取违反硬约束 #41
    DB_STATEMENT_CACHE_SIZE: int = 0
    # DB 启动是否强依赖。true: DB 连接失败直接中止启动（生产推荐）；false: 记录告警并降级继续（开发/无 DB 环境用）
    DB_STARTUP_REQUIRED: bool = True

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Assemble db connection."""
        if isinstance(v, str):
            return v
        data = info.data
        db_type = (data.get("DATABASE_TYPE") or "postgresql").lower()
        host = data.get("DATABASE_HOST") or data.get("POSTGRES_SERVER")
        port = data.get("DATABASE_PORT") or data.get("POSTGRES_PORT")
        name = data.get("DATABASE_NAME") or data.get("POSTGRES_DB")
        user = data.get("DATABASE_USER") or data.get("POSTGRES_USER")
        password = data.get("DATABASE_PASSWORD") or data.get("POSTGRES_PASSWORD")
        sqlite_path = data.get("DATABASE_SQLITE_PATH") or "./pygbsentry.db"
        if db_type in {"postgres", "postgresql", "kingbase", "kingbasees"}:  # 移除中文别名"人大金仓"，保留英文别名
            return str(PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=user,
                password=password,
                host=host,
                port=port,
                path=f"{name or ''}",
            ))

        if db_type in {"mysql"}:
            _safe_user = quote_plus(str(user or ""), safe="")
            _safe_pwd = quote_plus(str(password or ""), safe="")
            return f"mysql+aiomysql://{_safe_user}:{_safe_pwd}@{host}:{port}/{name}"
        if db_type in {"sqlite"}:
            normalized = sqlite_path.replace("\\", "/")
            if normalized.startswith("./") or normalized.startswith("../"):
                return f"sqlite+aiosqlite:///{normalized}"
            return f"sqlite+aiosqlite:///{normalized}"
        if db_type in {"dm", "dameng", "damengdb"}:  # 移除中文别名"达梦"，保留英文别名
            _safe_user = quote_plus(str(user or ""), safe="")
            _safe_pwd = quote_plus(str(password or ""), safe="")
            return f"dm+dmPython://{_safe_user}:{_safe_pwd}@{host}:{port}/{name}"  # S-06-04 达梦数据库使用dm+dmPython驱动而非mysql+aiomysql
        return str(PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=data.get("POSTGRES_USER"),
            password=data.get("POSTGRES_PASSWORD"),
            host=data.get("POSTGRES_SERVER"),
            port=data.get("POSTGRES_PORT"),
            path=f"{data.get('POSTGRES_DB') or ''}",
        ))

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Union[str, None] = None
    REDIS_DB: int = 0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 3.0
    REDIS_SOCKET_TIMEOUT: float = 3.0
    # Redis max_connections now configurable via env (default 50)
    REDIS_MAX_CONNECTIONS: int = 50
    # P1-fix [2026-07-17]: 完整 Redis URL（可选，留空时由 REDIS_HOST/PORT/PASSWORD 拼接）。
    # 原 plugin_manager.py 使用 getattr(settings, "REDIS_URL", None) 动态获取违反硬约束 #41
    REDIS_URL: Union[str, None] = None
    # 启动时是否连接 Redis。默认 False：无 Redis 时部分环境会长时间卡在 TCP，导致 8000 不监听；需要限流/会话时再设 true 并保证 redis-server 可用
    INIT_REDIS_ON_STARTUP: bool = False

    # --- Redis Sentinel / Cluster ---
    REDIS_SENTINEL_HOSTS: str = ""  # Redis Sentinel地址列表，格式: host1:port1,host2:port2,host3:port3
    REDIS_SENTINEL_MASTER: str = "mymaster"  # Redis Sentinel master名称
    REDIS_SENTINEL_PASSWORD: str = ""  # Redis Sentinel密码
    REDIS_CLUSTER_MODE: bool = False  # 是否使用Redis Cluster模式

    # 高可用 (HA) 与集群配置
    CLUSTER_ENABLED: bool = False
    CLUSTER_NODE_ID: str = "" # 如果为空，启动时自动生成 UUID
    # P1-fix [2026-07-17]: 多租户标识（用于 license:refresh 频道隔离等场景）。
    # 原 plugin_manager.py 使用 getattr(settings, "TENANT_ID", "") 动态获取违反硬约束 #41
    TENANT_ID: str = ""

    # SIP — 以下默认值仅供开发使用，生产环境必须在 .env 中显式配置
    SIP_IP: str = "0.0.0.0"
    SIP_TALK_DEFAULT_PORT: int = 6000
    SIP_PORT: int = 5060  # PRODUCTION: 必须在 .env 中设置，避免与其他 SIP 服务端口冲突
    # P1-fix [2026-07-17]: SIP 传输层协议 — 原 platforms.py 使用 getattr(settings, "SIP_TRANSPORT", "UDP")
    # 动态获取违反硬约束 #41。默认 UDP（与历史 getattr 默认值一致）
    SIP_TRANSPORT: str = "UDP"
    SIP_WS_PORT: int = 0  # SIP over WebSocket端口(0=禁用)
    # 移除重复的GB28181_VERSION定义（L162），保留L198的完整注释版本
    # SIPS (TLS) Support
    ENABLE_SIPS: bool = False
    SIPS_CERT_FILE: str = ""
    SIPS_KEY_FILE: str = ""
    STUN_SERVER: str = ""
    # SIP 启动是否强依赖。true: 端口占用等异常直接中止启动；false: 记录告警并降级继续
    SIP_STARTUP_REQUIRED: bool = True
    SIP_ID: str = "34020000002000000001"  # PRODUCTION: 必须在 .env 中设置唯一 SIP_ID（20位数字），多实例部署时每个实例必须不同
    SIP_DOMAIN: str = "3402000000"  # PRODUCTION: 必须在 .env 中设置为实际行政区划编码（10位数字）
    # 设备注册默认鉴权密码（当 Asset.password 为空/未创建时使用）
    SIP_DEFAULT_PASSWORD: str = ""  # MUST be set via .env or environment variable
    # FIX [2026-07-17 P1]: 补全弱密码列表文件路径配置项，原 main.py 使用 getattr 动态获取违反硬约束
    WEAK_PASSWORD_LIST_FILE: str = ""
    # 管理员初始/重置密码（首次创建admin用户或重置密码时使用）
    # 留空则首次启动自动生成随机密码并打印到日志；设置后每次启动都会重置admin密码
    ADMIN_INITIAL_PASSWORD: str = ""
    # 强制重置admin密码（需同时设置 ADMIN_INITIAL_PASSWORD）
    # 设为 true 时下次启动重置密码，重置后应删除此配置
    ADMIN_FORCE_RESET_PASSWORD: bool = False
    SIP_IP_BLACKLIST: str = ""  # 逗号分隔的黑名单IP，例如 "91.208.92.173,1.2.3.4"
    # SIP 调试开关：仅在联调时开启，输出关键头和 XML 摘要
    SIP_DEBUG_TRACE_ENABLED: bool = False
    # SIP 调试采样率：0.0~1.0（1.0=全量）
    SIP_TRACE_SAMPLE_RATE: float = 0.1
    # 主动级联：Keepalive 连续未收到 ACK 达到阈值后触发重注册
    SIP_PLATFORM_KEEPALIVE_MISS_THRESHOLD: int = 3
    SIP_TRANSACTION_T1_SECONDS: float = 0.5
    SIP_TRANSACTION_T2_SECONDS: float = 4.0
    SIP_INVITE_2XX_RETRANS_MAX_SECONDS: float = 32.0
    SIP_INVITE_ZLM_MAX_NODE_RETRIES: int = 3
    SIP_INVITE_ZLM_OPEN_RTP_TIMEOUT_SECONDS: float = 3.0
    # P1-fix [2026-07-17]: ZLM 关闭 RTP 端口超时（秒），原 zlm_rtp_server_service.py 使用
    # getattr(settings, "SIP_INVITE_ZLM_CLOSE_RTP_TIMEOUT_SECONDS", 3.0) 动态获取违反硬约束 #41
    SIP_INVITE_ZLM_CLOSE_RTP_TIMEOUT_SECONDS: float = 3.0
    SIP_RESPONSE_CACHE_TTL_SECONDS: int = 32
    SIP_RESPONSE_CACHE_MAX_SIZE: int = 50000
    SIP_MAX_INFLIGHT: int = 5000
    SIP_INVITE_RESPONSE_TIMEOUT_SECONDS: int = 20
    # FIX-LEAK: 全局字典定期清理配置 — 防止内存泄漏和竞态条件
    SIP_SEEN_REQUESTS_TTL_SECONDS: int = 300  # 请求去重缓存 TTL（秒），默认 5 分钟
    SIP_SEEN_REQUESTS_MAX_SIZE: int = 5000  # 请求去重缓存最大条目数
    SIP_SEEN_REQUESTS_CLEANUP_INTERVAL_SECONDS: int = 60  # 去重缓存定期清理间隔（秒）
    SIP_AUTH_FAILURE_CLEANUP_INTERVAL_SECONDS: int = 60  # 鉴权失败追踪清理间隔（秒）
    SIP_AUTH_FAILURE_MAX_SIZE: int = 5000  # 鉴权失败追踪字典最大条目数，超限触发清理
    SIP_CLEANUP_LOCKS_CLEANUP_INTERVAL_SECONDS: int = 300  # 设备清理锁回收间隔（秒）
    SIP_INVITE_TIMEOUT_SECONDS: int = 20
    # FIX: [2026-07-16] 以下配置项之前仅通过 getattr 使用，未在 Settings 中定义，
    # 导致无法通过 .env 覆盖。现在统一定义，支持 .env 配置。
    SIP_CASCADE_INVITE_TIMEOUT_SECONDS: int = 30  # 级联 INVITE 超时（秒），链路较长时需 >20s
    # P1-fix [2026-07-17]: 级联注册超时（秒），原 platform_service.py 使用 getattr(settings, "SIP_CASCADE_REGISTER_TIMEOUT_SECONDS", 5.0)
    # 动态获取违反硬约束 #41。默认 5 秒（与历史 getattr 默认值一致）
    SIP_CASCADE_REGISTER_TIMEOUT_SECONDS: float = 5.0
    SIP_PLATFORM_KEEPALIVE_TIMEOUT_SECONDS: float = 5.0  # 平台 keepalive 超时（秒）
    SIP_PLATFORM_KEEPALIVE_RETRIES: int = 1  # 平台 keepalive 重试次数
    SIP_IP_BLACKLIST_CACHE_TTL_SECONDS: float = 60.0  # IP 黑名单内存缓存 TTL（秒）

    ZLM_NONE_READER_DELAY_SECONDS: float = 0
    ZLM_TCP_ACTIVE_CONNECT_RETRIES: int = 6  # TCP-ACTIVE 设备连接重试次数（覆盖设备端口准备时间）
    ZLM_TCP_ACTIVE_CONNECT_DELAY: float = 0.5  # TCP-ACTIVE 重试间隔基数（秒，线性退避）

    # P1-fix [2026-07-17]: SIP 认证相关配置项必须在 Settings 类明确定义
    # 原代码通过 getattr(settings, "XXX", default) 动态获取，违反项目硬约束 #41
    SIP_AUTH_RELAXED: bool = False  # true 时放宽 stale nonce / nc 重放检查（兼容旧设备）
    SIP_DIGEST_NONCE_TTL_SECONDS: int = 300  # nonce 有效期（秒）
    SIP_DIGEST_FAIL_WINDOW_SECONDS: int = 300  # 认证失败滑动窗口（秒）
    SIP_DIGEST_FAIL_MAX_ATTEMPTS: int = 10  # 窗口内最大失败次数
    SIP_DIGEST_FAIL_LOCK_DURATION: int = 300  # 锁定时长（秒）
    SIP_DIGEST_FAIL_TRACKER_MAX_SIZE: int = 50000  # 失败追踪字典硬上限（防内存耗尽）

    # FIX [2026-07-29 P0]: EasyGBS 等非标准平台对 From/To URI host 使用 SIP_DOMAIN
    # (行政区划码) 的 MESSAGE 请求返回 400 Bad Request。实测 EasyGBS 自己发送的
    # REGISTER/MESSAGE 均使用 IP:port 作为 From URI host。设为 true 时，outgoing
    # SIP 请求的 From/To URI host 将使用 sip_via_host() (IP) 而非 SIP_DOMAIN。
    # 默认 true，因为绝大多数下级平台/设备均接受 IP host，而 EasyGBS 明确拒绝 SIP_DOMAIN host。
    SIP_FROM_TO_USE_IP: bool = True

    # P1-fix [2026-07-17]: SIP 模块补全配置项 — 原 getattr(settings, "XXX", default) 动态获取违反硬约束 #41
    SIP_REALM: str = ""  # SIP Digest realm（空则回退 SIP_DOMAIN/PROJECT_NAME）
    SIP_KEEPALIVE_SN_CACHE_MAX: int = 100000  # keepalive 序号去重缓存最大条目数
    SIP_NONCE_NC_MAX_SIZE: int = 10000  # nonce/nc 追踪字典最大条目数
    SIP_NONCE_NC_TTL_SECONDS: int = 300  # nonce/nc 追踪条目 TTL（秒）
    SIP_SSRC_WAITERS_MAX_SIZE: int = 5000  # SSRC 等待者字典最大条目数
    SIP_DIALOG_MAX_COUNT: int = 50000  # dialog 字典最大条目数
    SIP_DIALOG_TTL_SECONDS: int = 86400  # dialog 条目 TTL（秒）
    # SIP Session Timer (RFC 4028) — 长会话保活配置
    # P1-fix [2026-07-17]: 原 PyGBSentry 全库未实现 Session Timer，导致
    # 长时间点播/对讲/级联会话一方静默掉线后另一方永久持有僵尸会话。
    # 默认 1800 秒（30 分钟）与 RFC 4028 推荐值一致；Min-SE 90 秒防止恶意小值。
    SIP_SESSION_EXPIRES_SECONDS: int = 1800  # 默认 Session-Expires（秒）
    SIP_SESSION_MIN_SE_SECONDS: int = 90  # Min-SE 下限（秒），拒绝过小值
    SIP_SUBSCRIBE_MIN_EXPIRES: int = 60  # 订阅最小过期时间（秒）
    SIP_STRICT_BYE_TAG_MATCH: bool = False  # BYE 严格 tag 匹配
    SIP_IP_RATE_LIMIT: int = 100  # 单 IP 速率限制
    SIP_MAX_TCP_CLIENTS: int = 1000  # TCP 客户端最大连接数
    SIP_TCP_KEEPALIVE_INTERVAL_SECONDS: float = 30.0  # TCP keepalive 间隔（秒）
    SIP_TCP_KEEPALIVE_MAX_MISS: int = 3  # TCP keepalive 最大丢失次数
    SIP_INVITE_SERVER_TX_TTL_SECONDS: float = 120.0  # INVITE 服务端事务 TTL（秒）
    SIP_TRANSACTION_TIMEOUT_SECONDS: float = 30.0  # 事务超时（秒）
    SIP_INVITE_ZLM_MAX_PORT_RETRIES: int = 10  # INVITE ZLM 端口重试次数
    CASCADE_INVITE_TIMEOUT_SECONDS: int = 30  # 级联 INVITE 超时（秒）
    ALLOW_CASCADE_RELAY: bool = False  # 是否允许级联转发
    CASCADE_RTP_MEDIA_BYPASS: bool = True  # 级联 RTP 媒体旁路
    SIPS_PORT: int = 5061  # SIPS(TLS) 端口
    SIPS_CA_CERT_FILE: Union[str, None] = None  # SIPS CA 证书文件
    SSRC_CLEANUP_INTERVAL_SECONDS: float = 300.0  # SSRC 清理间隔（秒）
    SSRC_STALE_THRESHOLD_SECONDS: float = 3600.0  # SSRC 过期阈值（秒）
    PTZ_EMERGENCY_WHITELIST: str = ""  # PTZ 紧急控制白名单（逗号分隔）
    PTZ_MIN_INTERVAL_SECONDS: float = 0.1  # PTZ 最小指令间隔（秒）
    GB28181_PLAYBACK_SEEK_RAW: bool = False  # 回放拖动使用裸 NPT 数值
    MEDIA_SERVER_RTP_PROXY_PORT: int = 0  # 媒体服务器 RTP 代理端口（0=自动）
    CATALOG_MONITOR_INTERVAL_SECONDS: float = 60.0  # 目录响应清理周期（秒）
    CATALOG_ENTRY_TTL_SECONDS: float = 300.0  # 目录响应条目 TTL（秒）

    # 播放启动时 ZLM 流就绪探测参数
    PLAY_START_STREAM_READY_MAX_ATTEMPTS: int = 20  # 最大探测次数
    PLAY_START_STREAM_READY_INTERVAL: float = 0.25  # 探测间隔（秒）

    # FIX [2026-09-05 P1]: 部分 NVR 固件把未点播通道在目录里全部报 OFF（点播时才报 ON），
    # 平台照单全收导致「在线通道慢慢变少、同步又恢复」。开启后目录/通知中的 OFF 视为
    # 状态未知，不翻转通道在线状态；设备可达性以注册/心跳为准。
    CATALOG_IGNORE_OFF_STATUS: bool = True
    GB28181_SSRC_POLICY: str = "adaptive"
    GB28181_SSRC_RETRY_ON_NOT_READY: bool = True
    GB28181_SSRC_RETRY_ORDER: str = "strict,off"
    GB28181_AUTO_ENSURE_EMBEDDED_MEDIA_NODE: bool = True
    GB28181_VERSION: str = "2016"  # GB28181协议版本(2016/2022)，影响SDP a=track行等
    GB28181_STREAM_SWITCH_USE_TRACK_SUBJECT: bool = True  # 默认开启GB28181-2022码流切换track标识，与wvp对齐
    GB28181_PLAYBACK_SDP_TIME_FORMAT: str = "iso"  # 回放SDP时间格式(iso/epoch)
    GB28181_VIDEO_QUALITY: int = 0  # 视频质量等级(0=主码流,1=子码流)
    GB28181_CATALOG_SUBSCRIBE_EXPIRES: int = 3600  # 目录订阅过期时间(秒)
    GB28181_MOBILE_POSITION_SUBSCRIBE_INTERVAL: int = 5  # 移动位置订阅间隔(秒)
    GB28181_DEVICE_STATUS_QUERY_INTERVAL: int = 300  # 设备状态查询间隔(秒)
    GB28181_ALARM_SUBSCRIBE_EXPIRES: int = 3600  # 报警订阅过期时间(秒)

    # 允许未知的级联平台发来点播请求（例如对端填写了不匹配的 SIP ID，但我们依然给流）
    ALLOW_UNKNOWN_CASCADE_INVITE: bool = False

    # AI Vision Hub (optional). Default off to avoid heavy model downloads on startup.
    VISION_HUB_ENABLED: bool = False

    # AI Gateway (for ai_callback_url)
    AI_GATEWAY_SNAPSHOT_DIR: str = "ai_gateway_snapshots"
    AI_GATEWAY_MAX_SNAPSHOT_KB: int = 512
    AI_GATEWAY_FORWARD_UPSTREAM_URL: Union[str, None] = None
    AI_GATEWAY_FORWARD_TIMEOUT_SECONDS: int = 10

    # Plugin dependency auto-install (for self-contained AI plugins)
    PLUGIN_AUTO_INSTALL_DEPENDENCIES: bool = False  # 供应链安全, dev 环境可设 True
    PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS: int = 300
    PLUGIN_DEPENDENCY_VENDOR_DIR_NAME: str = ".vendor"
    # G-15: 插件依赖 venv 隔离（可选增强，与 .vendor 方式二选一）
    PLUGIN_VENV_ISOLATION_ENABLED: bool = False
    PLUGIN_VENV_DIR_NAME: str = ".venv"
    PLUGIN_MENU_PATH_REQUIRED_PREFIX: str = "/plugins/"

    # SIP 状态存储后端：local（单进程内存）/ redis（多进程共享）
    SIP_STATE_BACKEND: str = "local"
    SIP_STATE_BACKEND_REDIS_PREFIX: str = "gb:sip:state:"

    # Media Server
    MEDIA_SERVER_SECRET: str = ""  # MUST be set via .env or environment variable
    MEDIA_SERVER_HOST: str = "127.0.0.1"
    MEDIA_SERVER_HTTP_PORT: int = 8880
    MEDIA_SERVER_RTSP_PORT: int = 554
    MEDIA_SERVER_RTMP_PORT: int = 1935
    MEDIA_SERVER_RTP_PROXY_PORT: int = 30000
    # P1-fix [2026-07-17]: 媒体服务器 IP 与广播端口 — 原 stream_proxy.py 使用 getattr(settings, "MEDIA_SERVER_IP", settings.SIP_IP)
    # 和 getattr(settings, "MEDIA_SERVER_BROADCAST_PORT", 20000) 动态获取违反硬约束 #41
    MEDIA_SERVER_IP: str = ""  # 空则回退到 SIP_IP
    MEDIA_SERVER_BROADCAST_PORT: int = 20000
    # P1-fix [2026-07-17]: 流媒体公网 RTMP 端口 — 原 stream_proxy.py 使用 getattr(settings, "STREAM_PUBLIC_RTMP_PORT", 1935)
    # 动态获取违反硬约束 #41。默认 1935（与历史 getattr 默认值一致）
    STREAM_PUBLIC_RTMP_PORT: int = 1935
    # RTP端口范围扩展为1000个(30000-30999)，满足256路+并发流目标
    MEDIA_SERVER_RTP_PROXY_PORT_RANGE: str = "30000-30999"
    MEDIA_SERVER_RTP_STREAM_MODE: str = "UDP"
    MEDIA_SERVER_HTTPS_PORT: int = 0
    MEDIA_SERVER_RTSPS_PORT: int = 0
    MEDIA_SERVER_RTMPS_PORT: int = 0
    ZLM_RECORD_FILE_SECOND: int = 300
    ZLM_RECORD_SAMPLE_MS: int = 500
    ZLM_PROTOCOL_MP4_MAX_SECOND: int = 300
    ZLM_HTTP_PORT: int = 80
    ZLM_RTSP_PORT: int = 554
    ZLM_RTP_PORT: int = 0
    ZLM_API_SECRET: str = ""
    ZLM_API_BASE_URL: str = ""
    # ZLM HTTP connection pool tuning
    ZLM_POOL_MAX_CONNECTIONS: int = 50
    ZLM_POOL_KEEPALIVE_SECONDS: int = 30
    ZLM_POOL_TIMEOUT_SECONDS: float = 10.0
    # FIX: [2026-07-16 P0] Shared HTTP client (httpx) 配置项，原通过 getattr
    # 动态获取导致 .env 配置不生效。现在显式定义在 Settings 中。
    HTTP_CLIENT_TIMEOUT: float = 30.0
    HTTP_CLIENT_CONNECT_TIMEOUT: float = 10.0
    HTTP_CLIENT_MAX_CONNECTIONS: int = 100
    HTTP_CLIENT_MAX_KEEPALIVE: int = 20
    HTTP_CLIENT_VERIFY_SSL: bool = True
    # ZLM protocol defaults (0=disabled, 1=enabled)
    ZLM_DEFAULT_ENABLE_HLS: int = 0
    ZLM_DEFAULT_ENABLE_FLV: int = 1
    # P1-fix [2026-07-17]: ZLM 默认是否启用 MP4 录制 — 原 hook.py 使用
    # getattr(settings, "ZLM_DEFAULT_ENABLE_MP4", True) 动态获取违反硬约束 #41
    ZLM_DEFAULT_ENABLE_MP4: bool = True
    # ZLM node scheduling weights (should sum to 1.0)
    ZLM_SCHEDULE_WEIGHT_STREAMS: float = 0.5
    ZLM_SCHEDULE_WEIGHT_CPU: float = 0.3
    ZLM_SCHEDULE_WEIGHT_MEM: float = 0.2
    # Stream session cache TTL
    STREAM_SESSION_CACHE_TTL_SECONDS: int = 300
    # P1-fix [2026-07-17]: 默认值由 "localhost" 改为空字符串。
    # "localhost" 会导致远程客户端拿到指向自身的播放 URL，播放失败。
    # 空字符串时各调用方应回退到 MEDIA_SERVER_HOST 或 SIP_IP 并输出告警。
    STREAM_PUBLIC_HOST: str = ""
    STREAM_PUBLIC_HTTP_PORT: int = 8880
    STREAM_PUBLIC_SCHEME: str = "http"
    # P0-RTP: ZLM RTP Server 超时秒数，NAT场景下设备推流延迟可能超过ZLM默认15秒
    # 建议生产环境设置为30-60秒，可通过环境变量 RTP_SERVER_TIMEOUT_SECONDS 覆盖
    RTP_SERVER_TIMEOUT_SECONDS: int = int(os.getenv("RTP_SERVER_TIMEOUT_SECONDS", "30") or "30")
    # P0-RTP: RTP超时宽限期 — INVITE发送后多少秒内忽略ZLM的RTP超时回调
    # 在此期间收到超时回调时，重新打开RTP服务器而非清理会话
    RTP_TIMEOUT_GRACE_PERIOD_SECONDS: int = int(os.getenv("RTP_TIMEOUT_GRACE_PERIOD_SECONDS", "20") or "20")
    # P0-RTP: 别名，供 on_rtp_server_timeout / _cleanup_sessions 统一引用
    RTP_TIMEOUT_GRACE_SECONDS: int = int(os.getenv("RTP_TIMEOUT_GRACE_SECONDS", os.getenv("RTP_TIMEOUT_GRACE_PERIOD_SECONDS", "20") or "20") or "20")
    # P0-SIP: SIP 端口绑定重试配置（处理进程重启时旧端口未释放）
    SIP_BIND_MAX_RETRIES: int = int(os.getenv("SIP_BIND_MAX_RETRIES", "3") or "3")
    SIP_BIND_RETRY_DELAY: float = float(os.getenv("SIP_BIND_RETRY_DELAY", "1.0") or "1.0")
    # P0-fix: SIP socket 缓冲区与端口复用配置（应对 REGISTER 风暴与多实例 HA 部署）
    SIP_UDP_RCVBUF: int = int(os.getenv("SIP_UDP_RCVBUF", "4194304") or "4194304")  # 4MB
    SIP_UDP_SNDBUF: int = int(os.getenv("SIP_UDP_SNDBUF", "1048576") or "1048576")  # 1MB
    SIP_TCP_BACKLOG: int = int(os.getenv("SIP_TCP_BACKLOG", "1024") or "1024")
    SIP_REUSE_PORT: bool = str(os.getenv("SIP_REUSE_PORT", "false")).lower() in {"1", "true", "yes", "on"}

    # 快照相关配置
    SNAPSHOT_CONCURRENCY_LIMIT: int = 3
    SNAPSHOT_TTL_SECONDS: int = 60
    SNAPSHOT_EXISTING_TIMEOUT_SECONDS: float = 12.0
    SNAPSHOT_INVITE_TIMEOUT_SECONDS: float = 40.0
    SNAPSHOT_BATCH_CONCURRENCY: int = 5
    SNAPSHOT_BATCH_ITEM_TIMEOUT_SECONDS: float = 45.0
    SIP_INVITE_RATE_LIMIT_WINDOW_SECONDS: float = 5.0
    SIP_INVITE_RATE_LIMIT_PER_DEVICE: int = 8
    SIP_INVITE_RATE_LIMIT_PER_TENANT: int = 40
    # FIX: [2026-07-03] 全局并发 INVITE 数量限制，防止大流量时打爆设备 [全栈工程师]
    SIP_INVITE_MAX_CONCURRENT: int = 200
    # P4 magic numbers → config constants
    WATCHDOG_CALLBACK_TIMEOUT_SECONDS: int = 30
    DEVICE_OFFLINE_MAX_GRACE_SECONDS: int = 300
    SSRC_CLEANUP_MAX_AGE_SECONDS: int = 86400
    # 设备离线检测宽限时间（秒），last_keepalive超过此时间未更新则标记离线
    DEVICE_OFFLINE_GRACE_SECONDS: int = 60
    # TCP IP-only回退最大次数，超过后自动禁用（防止NAT环境路由错误）
    SIP_TCP_IP_ONLY_FALLBACK_MAX: int = 100
    STREAM_SLA_ENABLED: bool = True
    RECORD_DOWNLOAD_SIGN_ENABLED: bool = True
    RECORD_DOWNLOAD_SIGN_TTL_SECONDS: int = 900
    RECORD_DOWNLOAD_SIGN_SECRET: Union[str, None] = None
    SNAPSHOT_REFRESH_ENABLED: bool = True  # 默认开启定时快照刷新，与wvp对齐
    SNAPSHOT_REFRESH_INTERVAL_SECONDS: int = 1800
    SNAPSHOT_REFRESH_TTL_SECONDS: int = 86400
    SNAPSHOT_REFRESH_WINDOW_START_HOUR: int = 2
    SNAPSHOT_REFRESH_WINDOW_END_HOUR: int = 5
    SNAPSHOT_REFRESH_MAX_PER_CYCLE: int = 20
    SNAPSHOT_REFRESH_PREFER_EXISTING: bool = True
    SNAPSHOT_REFRESH_ALLOW_INVITE: bool = False
    STREAM_WAIT_READY_MAX_ATTEMPTS: int = 40
    STREAM_WAIT_READY_INTERVAL: float = 0.25
    MEDIA_SERVER_HOOK_BASE_URL: Union[str, None] = None
    HOOK_CALLBACK_TIMEOUT_SECONDS: int = 5
    # P1-fix [2026-07-17]: ZLM Hook 超时秒数，原 media_manager.py 使用 getattr(settings, "ZLM_HOOK_TIMEOUT_SEC", 15)
    # 动态获取违反硬约束 #41。默认 15 秒（与历史 getattr 默认值一致）
    ZLM_HOOK_TIMEOUT_SEC: int = 15
    MEDIA_NODE_HEALTHCHECK_TIMEOUT: int = 3
    TASK_SHUTDOWN_TIMEOUT_SECONDS: int = 30
    # 自动探测内网/公网 IP（用于“内置 ZLM 节点”默认值补全）
    AUTO_DETECT_LAN_IP: bool = True
    AUTO_DETECT_PUBLIC_IP: bool = True  # 默认开启公网IP探测，支持公网部署，与wvp对齐
    PUBLIC_IP_LOOKUP_URL: str = "https://api.ipify.org"
    PUBLIC_IP_LOOKUP_TIMEOUT_SECONDS: float = 2.0
    # 多流媒体节点集群（开源默认）：JSON 数组，如 [{"id":"zlm1","host":"127.0.0.1","http_port":8880,"rtp_port":30000,"public_host":"localhost","public_http_port":8880},...]。不配置或空则退化为单节点（使用 MEDIA_SERVER_*）。
    MEDIA_NODES: Optional[str] = None

    # 通道管理 /devices/tree（行政区划视图）：是否在树中按设备注册信息自动推断省市区并把设备挂到对应行政区节点（类似「注册即归类」）。
    # False（默认）：仅展示你手工挂载到行政区的目录/通道；设备平铺挂在根下「未分配行政区划」，避免注册污染区划树。
    CHANNEL_TREE_INFER_REGION_PLACEMENT: bool = True  # 默认开启注册即归类，与wvp对齐

    # Embedded ZLMediaKit deploy/build settings (Linux-only in open-source)
    # 是否启用“内置 ZLM”（禁用时平台不尝试下载/编译/启动内置 MediaServer；适合用户自建/外置 ZLM）
    EMBEDDED_ZLM_ENABLED: bool = True
    # lifespan 内 await media_manager.start 的超时（秒）。首次 ZLM 源码编译可能需数十分钟，默认 3600；设 0 表示不限时（不推荐生产）
    EMBEDDED_ZLM_START_TIMEOUT_SECONDS: int = 3600
    # 最优策略链：优先外置节点（DB media_nodes 或 MEDIA_NODES），命中则不启动内置 ZLM
    ZLM_PREFER_EXTERNAL_NODES: bool = True
    # 说明：线上 GitHub 可能不可达，支持用可访问的镜像 zip 覆盖源码下载地址
    ZLM_SOURCE_ZIP_URL: Union[str, None] = None
    # 可选兜底：提供预编译包下载地址（tar.gz 或 zip），用于源码无法下载/编译失败时回退
    ZLM_FALLBACK_BINARY_URL: Union[str, None] = None
    # ZLM 相关包（源码 zip / 预编译包 / ZLToolKit zip）单次下载总时长上限（秒）。
    # 超时即失败，防止低速网络下下载无限挂起阻塞部署；下载支持断点续传，下次重试会继续。
    ZLM_DOWNLOAD_MAX_SECONDS: int = 300
    # 若源码 zip 不包含 git submodules，可单独提供子模块压缩包下载地址（并解压到 3rdpart/ 下）
    ZLM_ZLTOOLKIT_ZIP_URL: Union[str, None] = None
    # 也可直接从 git 拉取源码（推荐：可包含 submodules），例如：https://github.com/ZLMediaKit/ZLMediaKit.git
    ZLM_GIT_URL: Union[str, None] = None
    # 可选：git 分支/Tag/Commit，默认 master
    ZLM_GIT_REF: Union[str, None] = None
    # ZLM 下载镜像自动选路：未显式配置 ZLM_GIT_URL / ZLM_SOURCE_ZIP_URL / ZLM_ZLTOOLKIT_ZIP_URL 时，
    # 并发探测 Gitee/GitHub 镜像首字节延迟并自动选最快源（国内服务器通常 Gitee 更快）。
    # 显式配置了上述 URL 时以用户配置为准，不做探测。设 false 关闭自动选路（固定使用 GitHub）。
    ZLM_MIRROR_AUTO_SELECT: bool = True
    # 是否允许从源码编译内置 ZLM（生产建议关闭，改用外置 ZLM 或预编译包）
    ZLM_BUILD_FROM_SOURCE: bool = False
    # 编译并发度（避免打满 CPU/内存）
    # - 0 表示自动按机器配置估算
    # - 1~8 表示固定值（优先级高于自动）
    ZLM_BUILD_JOBS: int = 0
    # 编译最低资源门槛（避免 1C1G/2C2G 直接“编译卡死”）
    # - 不满足门槛时：默认跳过源码编译并给出明确提示（可用 ZLM_BUILD_FORCE=true 强制）
    ZLM_BUILD_MIN_CPU: int = 2
    ZLM_BUILD_MIN_MEM_GB: int = 3
    ZLM_BUILD_FORCE: bool = False
    ZLM_AUTO_PORT_FALLBACK: bool = False
    ZLM_SSL_MERGED_PEM_PATH: Union[str, None] = None
    ZLM_REBUILD_IF_WEBRTC_MISSING: bool = False
    ZLM_STREAM_NONE_READER_DELAY_MS: int = 10000  # reduced from 600000ms (10min) to 10s to let app-layer control delay
    ZLM_WAIT_TRACK_READY_MS: int = 3000
    ZLM_WAIT_ADD_TRACK_MS: int = 1000
    ZLM_MAX_STREAM_WAIT_MS: int = 5000
    ZLM_HLS_SEG_DUR_SECONDS: int = 1
    ZLM_HLS_SEG_NUM: int = 3
    PLAY_ALLOW_NO_TOKEN: bool = False  # S-05 默认关闭无Token播放，生产环境必须认证
    AUTO_PLAY_ENABLED: bool = True  # 默认开启自动邀请，访问流URL时自动INVITE，与wvp对齐
    SSL_CERTBOT_ENABLED: bool = False
    SSL_CERTBOT_DOMAIN: str = ""
    SSL_CERTBOT_EMAIL: str = ""
    SSL_CERTBOT_MODE: str = "webroot"
    SSL_CERTBOT_WEBROOT_PATH: str = "/var/www/certbot"
    SSL_CERTBOT_RENEW_THRESHOLD_DAYS: int = 30
    SSL_CERTBOT_RENEW_CHECK_INTERVAL_HOURS: int = 12
    SSL_CERTBOT_RENEW_WINDOW_START_HOUR: int = 2
    SSL_CERTBOT_RENEW_WINDOW_END_HOUR: int = 5
    SSL_CERTBOT_CONFIG_DIR: str = "/etc/letsencrypt"
    SSL_CERTBOT_WORK_DIR: str = "/var/lib/letsencrypt"
    SSL_CERTBOT_LOGS_DIR: str = "/var/log/letsencrypt"
    SSL_CERTBOT_NGINX_RELOAD_CMD: str = "nginx -s reload"
    # 是否在生成的 ZLM config.ini 中写入 [rtc] 段（WebRTC 相关）。
    # 注意：不同 ZLM 版本的 rtc 配置键可能变化；写错会在 ZLM 日志出现 "unknow config" 并被忽略。
    # 默认 False：避免硬编码 8000/8001 引发误解或与后端端口配置混淆。
    ZLM_WRITE_RTC_SECTION: bool = True  # 默认开启WebRTC配置段，与wvp对齐
    # 仅当 ZLM_WRITE_RTC_SECTION=true 时生效
    MEDIA_SERVER_RTC_PORT: int = 8000  # 默认WebRTC端口8000，与wvp/ZLM默认配置对齐
    MEDIA_SERVER_RTC_TCP_PORT: int = 0
    # 回退策略：
    # - "nearby": 优先尝试接近原端口（按偏移序列），最后才用范围扫描
    # - "range": 直接用范围扫描
    ZLM_FALLBACK_PORT_STRATEGY: str = "nearby"
    # nearby 策略：依次尝试的端口偏移（逗号分隔），例如 100 会让 443 -> 543
    ZLM_FALLBACK_PORT_OFFSETS: str = "1,2,3,10,100,200,500,1000"
    # range 策略（或 nearby 最后兜底）：回退候选端口范围（含两端）
    ZLM_FALLBACK_PORT_START: int = 18000
    ZLM_FALLBACK_PORT_END: int = 18999

    # WebRTC TURN server (used by stream.py for WebRTC ICE configuration)
    TURN_SERVER: str = ""
    TURN_USERNAME: str = ""
    TURN_PASSWORD: str = ""

    # Firewall helper (Linux): print required ports and optionally auto-open
    # - AUTO_OPEN_PORTS=true 才会尝试修改防火墙（默认只打印提示）
    # - AUTO_OPEN_PORTS_DRY_RUN=true 仅打印将执行的命令（默认 true 更安全）
    # - AUTO_OPEN_PORTS_PROVIDER: auto|ufw|firewalld
    AUTO_OPEN_PORTS: bool = False
    AUTO_OPEN_PORTS_DRY_RUN: bool = True
    AUTO_OPEN_PORTS_PROVIDER: str = "auto"

    # Media nodes active probe (best-effort): periodically probe ZLM HTTP API
    # 用于在 Hook 不通时也能自动刷新 media_nodes 的 last_seen_at/is_online
    MEDIA_NODES_ACTIVE_PROBE_ENABLED: bool = True
    MEDIA_NODES_ACTIVE_PROBE_INTERVAL_SECONDS: int = 30

    # VOD / 录像配置
    VOD_ENABLE_PRELOAD: bool = True  # 默认开启VOD预加载，提升回放体验，与wvp对齐
    VOD_BUFFER_SIZE: int = 5000
    VOD_CACHE_DURATION: int = 30

    # P1-fix [2026-07-17]: S3 兼容存储配置 — 原 hook.py 使用 getattr(settings, "S3_XXX", "")
    # 动态获取违反硬约束 #41。默认空（不启用 S3 上传）
    S3_BUCKET: str = ""
    S3_ENDPOINT: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""

    # 流媒体质量与容错配置
    STREAM_DEFAULT_PROTOCOL: str = "http_flv"
    STREAM_BUFFER_TIME_MS: int = 1000
    STREAM_ENABLE_AUTO_RECONNECT: bool = True
    STREAM_TCP_FALLBACK: bool = True
    STREAM_QUALITY_MODE: str = "balance"
    STREAM_MIN_FPS: int = 20
    STREAM_MAX_PACKET_LOSS_RATE: float = 0.02
    STREAM_MIN_BUFFER_MS: int = 500
    STREAM_HEALTH_SCORE_MIN: int = 70

    PUSH_CHANNEL_MONITOR_ENABLED: bool = True
    PUSH_CHANNEL_MONITOR_INTERVAL_SECONDS: int = 10
    PUSH_CHANNEL_OFFLINE_GRACE_SECONDS: int = 20
    PUSH_CHANNEL_ENFORCE_STOPPED: bool = True

    PULL_PROXY_MONITOR_ENABLED: bool = True
    PULL_PROXY_MONITOR_INTERVAL_SECONDS: int = 10
    PULL_PROXY_OFFLINE_GRACE_SECONDS: int = 20
    PULL_PROXY_AUTO_RETRY_ENABLED: bool = True
    PULL_PROXY_AUTO_RETRY_MAX_COUNT: int = 5

    # Performance
    SIP_WORKER_CONCURRENCY: int = 200  # .env.example中写1000，需保持一致
    STREAM_SELF_HEAL_PROBE_ENABLED: bool = True

    SIP_TRACE_STORE_ENABLED: bool = True
    SIP_TRACE_STORE_SAMPLE_RATE: float = 1.0
    SIP_TRACE_STORE_MAX_PAYLOAD_LEN: int = 20000

    RECORD_SCHEDULE_EXECUTOR_ENABLED: bool = True
    RECORD_SCHEDULE_EXECUTOR_INTERVAL_SECONDS: int = 10

    RECORD_INDEX_VERIFY_ENABLED: bool = True
    RECORD_INDEX_VERIFY_INTERVAL_SECONDS: int = 60
    RECORD_INDEX_VERIFY_BATCH_SIZE: int = 50
    RECORD_INDEX_VERIFY_MAX_AGE_DAYS: int = 30
    STREAM_SELF_HEAL_PROBE_MIN_SUCCESS_TOTAL: int = 20
    STREAM_SELF_HEAL_PROBE_MAX_FAILURE_RATE: float = 10
    STREAM_SELF_HEAL_PROBE_MAX_IDLE_MINUTES: int = 60

    # Stream session cleanup
    STREAM_SESSION_CLEANUP_ENABLED: bool = True
    STREAM_SESSION_CLEANUP_INTERVAL_SECONDS: int = 60
    STREAM_SESSION_ZOMBIE_AGE_SECONDS: int = 300

    # Media node single-port multiplexing
    FORCE_SINGLE_PORT_MULTIPLEXING: bool = True
    HEALTH_ALERT_WEBHOOK_URL: Union[str, None] = None
    HEALTH_ALERT_MIN_HIGH_RISK: int = 3
    HEALTH_ALERT_HOLD_MINUTES: int = 5
    HEALTH_ALERT_COOLDOWN_MINUTES: int = 10
    # FIX: [2026-07-03] 系统资源监控配置 — 内存增长和磁盘空间告警 [可靠性工程师]
    MEMORY_GROWTH_ALERT_THRESHOLD_MB: int = 500  # 内存增长超过此值(MB)触发告警和缓存清理
    MEMORY_ABSOLUTE_ALERT_THRESHOLD_MB: int = 2048  # 内存绝对值超过此值(MB)标记降级
    DISK_SPACE_MONITOR_ENABLED: bool = True  # 是否启用磁盘空间监控
    DISK_SPACE_CRITICAL_THRESHOLD: int = 95  # 磁盘使用率超过此值(%)停止录像并告警
    DISK_SPACE_WARNING_THRESHOLD: int = 85  # 磁盘使用率超过此值(%)发出警告
    DISK_SPACE_RECOVERY_THRESHOLD: int = 80  # 磁盘使用率低于此值(%)恢复录像
    ALARM_ESCALATION_ENABLED: bool = True
    ALARM_ESCALATION_FIRST_MINUTES: int = 5
    ALARM_ESCALATION_MAX_LEVEL: int = 3
    ALARM_ESCALATION_PRIORITY_MINUTES: str = "1:2,2:5,3:10,4:15"
    SLA_BREACH_NOTIFY_ENABLED: bool = True
    SLA_BREACH_CONSECUTIVE_CYCLES: int = 3
    SLA_BREACH_WECHAT_WEBHOOK_URL: Union[str, None] = None
    SLA_BREACH_FEISHU_WEBHOOK_URL: Union[str, None] = None
    REPORT_DAILY_SEND_ENABLED: bool = False
    REPORT_DAILY_SEND_TIME_UTC: str = "01:00"
    REPORT_DAILY_WEBHOOK_URL: Union[str, None] = None
    REPORT_DAILY_EMAIL_TO: Union[str, None] = None

    # Webhook
    WEBHOOK_ALARM_URL: str = ""
    WEBHOOK_DEVICE_STATUS_URL: str = ""

    SMTP_HOST: Union[str, None] = None
    SMTP_PORT: int = 25
    SMTP_USERNAME: Union[str, None] = None
    SMTP_PASSWORD: Union[str, None] = None
    SMTP_USE_TLS: bool = False
    SMTP_FROM: Union[str, None] = None
    LICENSE_SIGNING_SECRET: Union[str, None] = None
    LICENSE_ED25519_PUBLIC_KEY: Union[str, None] = None
    LICENSE_ED25519_PRIVATE_KEY: Union[str, None] = None
    LICENSE_OFFLINE_PUBLIC_KEY: Union[str, None] = None
    ENTERPRISE_OFFLINE_LICENSE_REQUIRED: bool = False
    PLUGIN_LICENSE_OFFLINE_GRACE_PERIOD_SECONDS: int = 86400
    # 防盗版层级开关（初期简化策略：只开3层核心，其余默认关闭）
    # 第1层：安装校验（install-check）—— 始终开启
    # 第2层：本地 Ed25519 验签 —— 始终开启（需配置公钥）
    # 第3层：在线状态查询 —— 始终开启
    # 第4层：机器码绑定 —— 默认开启
    # 第5层：激活令牌 —— 默认开启
    # 第6层：包完整性校验 —— 默认开启（生产环境强制 package_sha256 + package_signature）
    PLUGIN_LICENSE_MACHINE_CODE_ENABLED: bool = True
    PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED: bool = True
    PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD: bool = True
    APP_EDITION: str = "oss"
    # 演示模式：为 true 时开放 /api/v1/demo/* 并返回内置演示设备数据，供新用户体验
    DEMO_MODE: bool = False
    COMMERCIAL_MODEL: str = "oss_open"
    COMMUNITY_PLAN_CODE: str = "community"
    # P1-fix [2026-07-17]: 本地计费套餐配置 — 原 billing.py 使用 getattr(settings, "LOCAL_BILLING_PLANS", None)
    # 动态获取违反硬约束 #41。默认 None（使用兜底 community 套餐）
    LOCAL_BILLING_PLANS: Union[list, None] = None
    SUBSCRIPTION_REMINDER_DAYS: int = 7
    TRIAL_REMINDER_DAYS: int = 7
    TRIAL_DAYS: int = 7
    SUBSCRIPTION_REMINDER_WEBHOOK_URL: Union[str, None] = None
    PLUGIN_MARKETPLACE_BASE_URL: str = ""  # 移除硬编码域名，强制env配置
    # 开源版「购买」按钮跳转的服务器版插件商城页，不填则用 PLUGIN_MARKETPLACE_BASE_URL
    PLUGIN_MARKETPLACE_SHOP_URL: Union[str, None] = None
    # 服务器版插件记录：安装/卸载时 POST 到此 URL，用于验证登录并记录购买、安装记录
    PLUGIN_SERVER_RECORD_URL: Union[str, None] = None
    # 插件商城公共 API 地址（面向所有用户，只读）
    # 用于：市场目录浏览、插件详情、license/check-status
    # PLUGIN_MARKETPLACE_BASE_URL 已在上方定义
    # 插件商城管理 API 地址（面向已注册的 OSS 实例，需 HMAC 认证）
    # 用于：OSS 实例注册/注销/心跳、install-check
    # 若未配置，则回退到 PLUGIN_MARKETPLACE_BASE_URL
    PLUGIN_MARKETPLACE_SERVER_URL: str = ""
    # ── 插件市场开关（开源版默认关闭）───────────────────────────────
    # 为 true 时启用插件市场功能（购买、市场目录、server API 调用、Redis 订阅）
    # 为 false 时所有市场相关功能静默降级（返回空列表/404），不连接任何外部 API
    # 独立部署开源版时应保持 false；连接服务器版时应设为 true
    PLUGIN_MARKETPLACE_ENABLED: bool = False
    # ──────────────────────────────────────────────────────────────
    # 开源版代理 /purchased 与运行时「已购」校验的内存缓存秒数（0 表示不缓存）
    PLUGIN_PURCHASED_PROXY_CACHE_SECONDS: int = 45
    # True：访问 paid 的 /plugins/runtime/* 与 /plugins/plugin-assets/* 时，在已配服务器 base 的前提下每次请求 POST install-check（与安装预检同源），成功后刷新已购代理缓存；False：仅用 /purchased 代理（受 PLUGIN_PURCHASED_PROXY_CACHE_SECONDS 影响）
    PLUGIN_PAID_RUNTIME_INSTALL_CHECK: bool = True
    # 已配服务器 base 且插件为 paid 时：True=install-check 必须成功（含网络错误则阻断）；False=与旧版类似，仅 401/402 阻断，其余异常不拦截
    PLUGIN_PAID_INSTALL_CHECK_STRICT: bool = True
    # 付费插件 runtime 授权策略（推荐直接使用该字段；旧字段仍兼容）：
    # - compat: 兼容旧逻辑（由 PLUGIN_PAID_RUNTIME_INSTALL_CHECK/PLUGIN_PAID_INSTALL_CHECK_STRICT 推导）
    # - cache_only: 仅依赖 /purchased 代理缓存
    # - online_strict: 每次走服务器 install-check（可命中短缓存），网络/异常也阻断（fail-close）
    # - online_fail_open: 每次走服务器 install-check（可命中短缓存），仅 401/402/403 阻断，网络/异常降级为本地已购缓存
    # - online_prefer_cache: 先查本地已购缓存，不命中再走 online_strict
    PLUGIN_PAID_RUNTIME_AUTH_MODE: str = "compat"
    # runtime 在线授权校验结果短缓存（秒）；用于降低高频页面轮询时对服务器版压力。0 表示不缓存
    PLUGIN_PAID_RUNTIME_ONLINE_CHECK_CACHE_SECONDS: int = 15
    # 付费插件 Hook（除 on_startup/on_shutdown/on_uninstall）每次触发前重验 license 的最小间隔（秒）；0=每次都读盘校验
    PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS: int = 60
    # 付费插件 license 后台周期重验（用于与服务器版权益状态保持更强一致）
    PLUGIN_PAID_LICENSE_SYNC_ENABLED: bool = True
    # <=0 时回退使用 PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS；两者都 <=0 则关闭周期重验
    PLUGIN_PAID_LICENSE_SYNC_INTERVAL_SECONDS: int = 0
    # T1-02: license 在线状态查询间隔（秒）；服务器 `/license/check-status` 调用，默认 300（5 分钟）
    PLUGIN_LICENSE_ONLINE_CHECK_INTERVAL_SECONDS: int = 300
    PLUGIN_LICENSE_ONLINE_CHECK_STRICT: bool = True
    PLUGIN_SERVER_INSTANCE_ENABLED: bool = True
    PLUGIN_LICENSE_DAILY_CHECK_MODE: bool = False
    # T1-05: OSS 实例信息持久化文件路径（重启后恢复 instance_id / instance_secret）
    OSS_INSTANCE_INFO_FILE: str = "data/oss_instance.json"
    # FIX [2026-07-17 P1]: 补全 OSS 实例心跳间隔配置项，原 main.py 使用 getattr 动态获取违反硬约束
    OSS_INSTANCE_HEARTBEAT_INTERVAL_SECONDS: int = 300
    # 每轮 sleep 抖动（秒），避免多实例同秒请求服务器；0 表示关闭抖动
    PLUGIN_PAID_LICENSE_SYNC_JITTER_SECONDS: int = 5
    # 启动后是否立即执行一次重验（建议开启）
    PLUGIN_PAID_LICENSE_SYNC_ON_STARTUP: bool = True
    # 插件 Hook 执行超时隔离（同进程）：秒；0 表示不启用。用于避免 Hook 卡死/长耗时阻塞主事件循环。
    PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS: float = 30.0
    # 插件 Hook 超时隔离模式：
    # - "thread": 同进程线程池 wait_for 超时跳过（默认/历史行为）
    # - "process": 尝试进程级执行同步回调，并在超时后 terminate 子进程（需要参数可 pickle；否则回退到 thread）
    PLUGIN_HOOK_EXEC_TIMEOUT_MODE: str = "thread"
    # plugin.json 可选 manifest_signature（Ed25519）；未配置公钥时若包内带签名则安装失败。为 true 时强制每条 manifest 必须带有效签名
    PLUGIN_MANIFEST_ED25519_PUBLIC_KEY: Union[str, None] = None
    PLUGIN_MANIFEST_SIGNATURE_REQUIRED: bool = False
    # plugin 包（ZIP 整包）签名（Ed25519）：当 catalog 提供 package_signature 时用于验签
    PLUGIN_PACKAGE_ED25519_PUBLIC_KEY: Union[str, None] = None
    # 强制 catalog 必须提供 package_signature（默认 false）
    PLUGIN_PACKAGE_SIGNATURE_REQUIRED: bool = True
    PLUGIN_UPGRADE_ALLOW_DOWNGRADE: bool = False
    # 升级失败回滚：对“已安装插件升级”默认先做目录快照再覆盖。
    PLUGIN_UPGRADE_BACKUP_ENABLED: bool = True
    # 升级快照目录（相对 backend 根目录）；空则默认 plugins/.upgrade_backups
    PLUGIN_UPGRADE_BACKUP_DIR: str = "plugins/.upgrade_backups"
    # 为 true 时，on_upgrade 回调出现失败/超时将阻断升级；false 时仅告警并继续。
    PLUGIN_UPGRADE_HOOK_STRICT: bool = False
    # 为 true 时，plugin.json.tables 中每个表名须以小写前缀 plugin_{id}_ 开头（id 中 - 视为 _）
    PLUGIN_TABLES_REQUIRE_PLUGIN_ID_PREFIX: bool = True
    # ── 插件沙箱资源限制 ──────────────────────────────────────────────
    # 单个插件最大CPU占用百分比（0=不限制）；超出后 Hook 执行被降级/跳过
    PLUGIN_SANDBOX_CPU_LIMIT_PERCENT: int = 30
    # 单个插件最大内存占用MB（0=不限制）；超出后 Hook 执行被降级/跳过
    PLUGIN_SANDBOX_MEMORY_LIMIT_MB: int = 256
    # 单个插件最大磁盘占用MB（0=不限制）；安装时检查，超出则拒绝安装
    PLUGIN_SANDBOX_DISK_LIMIT_MB: int = 500
    # 插件运行时危险API拦截（阻止插件在运行时导入/调用危险模块）
    PLUGIN_SANDBOX_RUNTIME_API_BLOCK_ENABLED: bool = True
    # 插件健康检查间隔秒数（0=关闭）
    PLUGIN_HEALTH_CHECK_INTERVAL_SECONDS: int = 60
    # 插件连续错误次数阈值，超过后自动禁用（0=不自动禁用）
    PLUGIN_HEALTH_ERROR_THRESHOLD: int = 10
    # 插件崩溃后自动重启次数上限（0=不自动重启）
    PLUGIN_HEALTH_AUTO_RESTART_LIMIT: int = 3
    # ── 插件卸载数据保留策略 ──────────────────────────────────────────
    # 默认卸载策略：cascade_delete | preserve | ask
    PLUGIN_UNINSTALL_DEFAULT_DATA_POLICY: str = "cascade_delete"
    # ── 插件安全扫描 ──────────────────────────────────────────────
    # 是否启用插件包安全扫描（安装/升级时检查危险API和依赖风险）
    PLUGIN_SECURITY_SCAN_ENABLED: bool = True
    # 扫描命中后是否阻断安装（False 时仅告警）
    PLUGIN_SECURITY_SCAN_BLOCK_ON_HIT: bool = True
    # 单次扫描最大文件数
    PLUGIN_SECURITY_SCAN_MAX_FILE_COUNT: int = 200
    # 单文件最大扫描字节数
    PLUGIN_SECURITY_SCAN_MAX_FILE_BYTES: int = 200_000
    # 单次扫描最大命中数
    PLUGIN_SECURITY_SCAN_MAX_HITS: int = 20
    PAYMENT_CALLBACK_SECRET: Union[str, None] = None
    PAYMENT_SUCCESS_RETURN_URL: str = ""  # 移除硬编码域名，强制env配置
    # P1-fix [2026-07-17]: 发布中心确认令牌 — 原 release_center.py 使用
    # getattr(settings, "RELEASE_CONFIRM_TOKEN", "") 动态获取违反硬约束 #41。默认空（未配置时发布接口拒绝）
    RELEASE_CONFIRM_TOKEN: str = ""

    ZLM_REQUEST_TIMEOUT_SHORT: int = 2
    ZLM_REQUEST_TIMEOUT_MEDIUM: int = 5
    ZLM_REQUEST_TIMEOUT_LONG: int = 10
    ZLM_REQUEST_TIMEOUT_EXTRA_LONG: int = 20
    UVICORN_TIMEOUT_KEEP_ALIVE: int = 5
    HEALTH_CHECK_LIMIT: int = 500
    NOTIFY_REQUEST_TIMEOUT: int = 3
    SERVER_PORT: int = 8000  # PRODUCTION: 必须在 .env 中设置，确保与反向代理/防火墙配置一致

    # R24-07: 使用 Pydantic v2 SettingsConfigDict 替代 class Config
    # extra="ignore" 对 BaseSettings 是必要的（env 变量常被多服务共享），
    # 但对 API 请求模型应使用 extra="forbid"
    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _enforce_prod_redis_on_startup(self):
        """Internal helper:  enforce prod redis on startup."""
        # P1-3: 生产环境强制 INIT_REDIS_ON_STARTUP=True
        # 限流/会话/Token吊销/黑名单等功能强依赖 Redis，生产关闭会引入安全风险
        _env = (self.APP_ENV or "dev").lower()
        if _env in {"prod", "production"} and not self.INIT_REDIS_ON_STARTUP:
            raise ValueError(
                "INIT_REDIS_ON_STARTUP must be True in production (APP_ENV=prod). "
                "Redis is required for rate limiting, session management, token revocation, and IP blacklist."
            )
        return self


settings = Settings()

if not settings.SECRET_KEY:
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "SECURITY: SECRET_KEY is empty in production! Refusing to start. "
            "Please set SECRET_KEY in your .env file."
        )
        raise SystemExit(1)
    else:
        import warnings
        generated = _secrets.token_hex(32)
        settings.SECRET_KEY = generated
        warnings.warn(
            "SECRET_KEY is not set in .env. A random key was generated for this session, "
            "but all JWT tokens will be invalidated on restart. "
            "Please set SECRET_KEY in your .env file for production use.",
            stacklevel=2,
        )

# FIX: [2026-07-10] FIELD_ENCRYPTION_KEY 空值在生产环境应 fail-fast，
# 而非等到运行时 field_crypto.encrypt_field 才抛 ValueError（导致设备注册/编辑功能静默不可用）。
# 与 SECRET_KEY 生产检查保持一致的语义。[全栈工程师]
if not settings.FIELD_ENCRYPTION_KEY:
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "SECURITY: FIELD_ENCRYPTION_KEY is empty in production! Refusing to start. "
            "Field-level encryption (device/platform passwords) requires a dedicated key. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        raise SystemExit(1)
    else:
        import warnings
        warnings.warn(
            "FIELD_ENCRYPTION_KEY is not set. Device/platform password encryption will fail at runtime. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"",
            stacklevel=2,
        )

# FIXED-P2: 生产环境已知弱密钥检测，防止部署时仅改 APP_ENV 而忘记替换密钥
# FIX: [2026-07-16 P0] 扩展黑名单，覆盖 .env.prod.example 中的占位符和常见弱密钥
_KNOWN_WEAK_SECRETS = {
    "test-verification-secret-key-not-for-production",
    "changeme",
    "change_me",
    "change_me_generate_a_strong_password",
    "secret",
    "your-secret-key",
    "example-secret-key",
    # .env.prod.example 占位符（用户照搬示例文件部署时会被检测到）
    "CHANGE_ME_GENERATE_A_RANDOM_64_CHAR_HEX_STRING",
    "CHANGE_ME_GENERATE_A_RANDOM_SECRET",
    "CHANGE_ME_GENERATE_A_STRONG_SIP_PASSWORD",
    "CHANGE_ME_GENERATE_A_STRONG_PASSWORD",
    "CHANGE_ME_REQUIRED",
    "CHANGE_ME",
    # 常见项目名+弱密码组合
    "pygbsentry-secret-key",
    "***REMOVED***",
    "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
}
import re as _re_weak_secret
# FIX: [2026-07-16 P0] 正则检测 CHANGE_ME / replace-with 前缀的密钥
_WEAK_SECRET_PATTERNS = [
    _re_weak_secret.compile(r"^CHANGE_ME", _re_weak_secret.IGNORECASE),
    _re_weak_secret.compile(r"^replace-with", _re_weak_secret.IGNORECASE),
    _re_weak_secret.compile(r"^YOUR_", _re_weak_secret.IGNORECASE),
    # 形如 "a1b2c3d4..." 的交替字母数字模式
    _re_weak_secret.compile(r"^([a-z][0-9])+$", _re_weak_secret.IGNORECASE),
    # 形如 "key-2024" / "secret-2026" 等项目名+年份模式
    _re_weak_secret.compile(r"^[a-z]+-?(secret|key|password)-?\d{2,4}$", _re_weak_secret.IGNORECASE),
]
_app_env = (settings.APP_ENV or "dev").lower()


def _is_weak_secret(key_value: str) -> bool:
    """FIX: [2026-07-16 P0] 统一弱密钥检测：黑名单 + 正则模式。"""
    if not key_value or key_value in _KNOWN_WEAK_SECRETS:
        return True
    for pattern in _WEAK_SECRET_PATTERNS:
        if pattern.match(key_value):
            return True
    return False


if _app_env in {"prod", "production"}:
    # FIX: [2026-07-16 P0] 使用统一的 _is_weak_secret 检测，覆盖黑名单和正则模式
    if _is_weak_secret(settings.SECRET_KEY):
        import logging as _logging
        _logging.getLogger(__name__).error(
            f"SECURITY: SECRET_KEY is set to a known weak value '{settings.SECRET_KEY[:8]}...'. "
            f"This is insecure in production. Please set a unique, strong SECRET_KEY in your .env file."
        )
        raise SystemExit(1)
    if _is_weak_secret(settings.MEDIA_SERVER_SECRET):
        import logging as _logging
        _logging.getLogger(__name__).error(
            f"SECURITY: MEDIA_SERVER_SECRET is set to a known weak value '{settings.MEDIA_SERVER_SECRET[:8]}...'. "
            f"This is insecure in production. Please set a unique, strong MEDIA_SERVER_SECRET in your .env file."
        )
        raise SystemExit(1)

# FIXED: [2026-07-10] 插件签名验签公钥配置一致性检查
# 商业化链路：用户从官网下载的签名插件包在 OSS 安装时需验签。
# 若签名要求开启但公钥未配置，所有签名插件安装都会失败。
_pkg_sig_req = settings.PLUGIN_PACKAGE_SIGNATURE_REQUIRED
_man_sig_req = settings.PLUGIN_MANIFEST_SIGNATURE_REQUIRED
_pkg_pub = (settings.PLUGIN_PACKAGE_ED25519_PUBLIC_KEY or "").strip()
_man_pub = (settings.PLUGIN_MANIFEST_ED25519_PUBLIC_KEY or "").strip()
_license_pub = (settings.LICENSE_ED25519_PUBLIC_KEY or "").strip()
if (_pkg_sig_req or _man_sig_req or _app_env in {"prod", "production"}) and not (_pkg_pub or _man_pub or _license_pub):
    import warnings as _warnings
    _warnings.warn(
        "插件签名验签公钥未配置：PLUGIN_PACKAGE_ED25519_PUBLIC_KEY / PLUGIN_MANIFEST_ED25519_PUBLIC_KEY / "
        "LICENSE_ED25519_PUBLIC_KEY 均为空。从官网下载的签名插件包将无法安装（验签失败）。"
        "请从官网获取插件签名公钥并配置到 .env 中。",
        stacklevel=2,
    )

# 数据库密码空值检查（仅对需要密码的数据库类型）
_db_type = (settings.DATABASE_TYPE or "postgresql").lower()
if _db_type not in {"sqlite"}:
    db_password = settings.DATABASE_PASSWORD or settings.POSTGRES_PASSWORD
    if not db_password:
        import warnings
        warnings.warn(
            "DATABASE_PASSWORD / POSTGRES_PASSWORD is not set. "
            "Database connection may fail. Please set it in your .env file.",
            stacklevel=2,
        )

# SQLite not suitable for production - block startup in production environment
if _db_type == "sqlite":
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "FATAL: SQLite is not suitable for production use with concurrent devices. "
            "Please set DATABASE_TYPE=postgresql (or mysql) and configure the connection in .env."
        )
        raise SystemExit(1)
    else:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "SQLite is being used in development mode. "
            "Do NOT use SQLite in production — it cannot handle concurrent device registrations. "
            "Set DATABASE_TYPE=postgresql and configure the connection in .env for production."
        )

# MEDIA_SERVER_SECRET 空值自动生成（仅开发环境）
if not settings.MEDIA_SERVER_SECRET:
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env not in {"prod", "production"}:
        settings.MEDIA_SERVER_SECRET = _secrets.token_hex(32)
        import logging as _logging
        _logging.getLogger(__name__).info(
            "MEDIA_SERVER_SECRET auto-generated for dev environment. "
            "Set a fixed value in .env for production."
        )

# MEDIA_SERVER_SECRET 生产环境空值检查
if not settings.MEDIA_SERVER_SECRET:
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "SECURITY: MEDIA_SERVER_SECRET is empty in production! Refusing to start. "
            "Please set a unique secret in your .env file."
        )
        raise SystemExit(1)
    else:
        import warnings
        warnings.warn(
            "MEDIA_SERVER_SECRET is not set. Auto-generated for this session. "
            "Please set a unique secret in your .env file for production use.",
            stacklevel=2,
        )

# SIP_DEFAULT_PASSWORD 生产环境空值阻断  # was warning-only, now blocks startup in production
if not settings.SIP_DEFAULT_PASSWORD:
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).critical(
            "FATAL: SIP_DEFAULT_PASSWORD is empty in production. "
            "Device registration would proceed without authentication. "
            "Set a strong password in your .env file to start."
        )
        raise SystemExit(1)

# SIP_STATE_BACKEND=local in production: error + mark readiness as degraded
if (settings.SIP_STATE_BACKEND or "local").strip().lower() == "local":
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "SECURITY: SIP_STATE_BACKEND is 'local' in production. "
            "Nonce/NC replay checks and INVITE rate limits are NOT shared across instances. "
            "Set SIP_STATE_BACKEND=redis and INIT_REDIS_ON_STARTUP=True in .env for multi-instance deployments. "
            "Readiness probe will report degraded until this is fixed."
        )

# PLUGIN_AUTO_INSTALL_DEPENDENCIES in production warns about supply chain risks
if settings.PLUGIN_AUTO_INSTALL_DEPENDENCIES:
    _app_env = (settings.APP_ENV or "dev").lower()
    if _app_env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "SECURITY: PLUGIN_AUTO_INSTALL_DEPENDENCIES is enabled in production! "
            "This allows runtime dependency installation which poses supply chain risks. "
            "Consider using a private PyPI mirror or pre-built plugin packages."
        )

# 启动时检测默认SIP_ID/SIP_DOMAIN，发出告警避免多套部署信令冲突
if settings.SIP_ID == "34020000002000000001":
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "SIP_ID is using the default value '34020000002000000001'. "
        "If running multiple PyGBSentry instances, each MUST have a unique SIP_ID "
        "to prevent signaling conflicts. Set SIP_ID in your .env file."
    )
if settings.SIP_DOMAIN == "3402000000":
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "SIP_DOMAIN is using the default value '3402000000'. "
        "Set SIP_DOMAIN to your actual administrative code in .env."
    )
if settings.SIP_PORT == 5060:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "SIP_PORT is using the default value 5060. "
        "Ensure this does not conflict with other SIP services on the same host. Set SIP_PORT in your .env file."
    )
if settings.SERVER_PORT == 8000:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "SERVER_PORT is using the default value 8000. "
        "Ensure this matches your reverse proxy / firewall configuration. Set SERVER_PORT in your .env file."
    )

# R3-06 SIP_ID/SIP_DOMAIN空字符串也必须通过格式校验，防止生成无效SIP URI
import re as _re
if not _re.match(r'^\d{20}$', str(settings.SIP_ID or "")):
    raise RuntimeError(f"SECURITY: SIP_ID must be 20 digits per GB28181, got: '{settings.SIP_ID}'")
if not _re.match(r'^\d{10}$', str(settings.SIP_DOMAIN or "")):
    raise RuntimeError(f"SECURITY: SIP_DOMAIN must be 10 digits per GB28181, got: '{settings.SIP_DOMAIN}'")

# RTP端口范围一致性校验 — 检测 MEDIA_SERVER_RTP_PROXY_PORT_RANGE 与 Docker 端口映射是否匹配
_rtp_range = (settings.MEDIA_SERVER_RTP_PROXY_PORT_RANGE or "").strip()
if _rtp_range and "-" in _rtp_range:
    try:
        _rtp_start, _rtp_end = _rtp_range.split("-", 1)
        _rtp_start, _rtp_end = int(_rtp_start.strip()), int(_rtp_end.strip())
        _rtp_span = _rtp_end - _rtp_start + 1
        # FIXED: 仅在 Docker 环境中警告端口范围过大（Docker 需要逐个映射端口）
        # 非 Docker 环境（物理机/VM）不受 Docker 端口映射限制，无需警告
        _is_docker = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
        if _rtp_span > 200 and _is_docker:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"RTP port range {_rtp_range} spans {_rtp_span} ports, which exceeds the "
                f"typical Docker mapping of 200 ports (30000-30199). If running in Docker, "
                f"ensure the port mapping in docker-compose.yml covers the full range, "
                f"or reduce MEDIA_SERVER_RTP_PROXY_PORT_RANGE to '30000-30199'."
            )
    except (ValueError, TypeError) as _exc:
        import logging as _logging
        _logging.getLogger(__name__).debug(f"RTP port range validation skipped: {_exc}")

# FIXED-P2: 端口冲突预检 — 检测 SIP_PORT / SERVER_PORT / MEDIA_SERVER_HTTP_PORT / MEDIA_SERVER_RTC_PORT 之间的冲突
_port_fields = {
    "SERVER_PORT": settings.SERVER_PORT,
    "SIP_PORT": settings.SIP_PORT,
    "MEDIA_SERVER_HTTP_PORT": settings.MEDIA_SERVER_HTTP_PORT,
}
if settings.ZLM_WRITE_RTC_SECTION:
    _port_fields["MEDIA_SERVER_RTC_PORT"] = settings.MEDIA_SERVER_RTC_PORT
_seen_ports: dict[int, str] = {}
for _fname, _pval in _port_fields.items():
    if _pval in _seen_ports:
        import logging as _logging
        _logging.getLogger(__name__).error(
            f"PORT CONFLICT: {_fname}={_pval} conflicts with {_seen_ports[_pval]}={_pval}. "
            f"This will cause one of the services to fail to bind. "
            f"Please change one of them in your .env file."
        )
    else:
        _seen_ports[_pval] = _fname


def sip_host_for_contact() -> str:
    """
    返回用于 SIP Contact 头部的"暴露给外部的主机地址"（可以是域名或IP）。
    优先级：
    1. BACKEND_PUBLIC_HOST（显式配置）
    2. STREAM_PUBLIC_HOST（流媒体公网配置）
    3. 自动检测内网 IP
    """
    # 优先使用显式配置
    host = settings.BACKEND_PUBLIC_HOST
    if host and host != "localhost":
        return host

    host = settings.STREAM_PUBLIC_HOST
    if host and host != "localhost":
        return host

    # 回退：使用 SIP 监听 IP（通常对内可达）
    return settings.SIP_IP or "127.0.0.1"


# 缓存 Via/Call-ID 用的 IP 地址，避免每次发包都做 DNS 解析
_sip_via_ip_cache: str | None = None


def sip_via_host() -> str:
    """
    返回用于 SIP Via/Call-ID 头部的 IP 地址（非域名）。

    FIX [2026-07-29 P0]: 实测发现 EasyGBS 等非标准 SIP 客户端对 Via 头中的
    域名（如 pygbsentry.jjtt.net）无法正确解析，会直接返回 400 Bad Request。
    真实 GB28181 抓包（LiveGBS / 海康 / 大华）均使用 IP 地址作为 Via host
    和 Call-ID host，From/To host 仍使用 SIP_DOMAIN（行政区划码）。

    本函数将 BACKEND_PUBLIC_HOST 域名解析为 IP 地址，解析失败时回退到
    自动检测的本地 IP。结果全局缓存，避免重复 DNS 查询。

    优先级：
    1. 如果 BACKEND_PUBLIC_HOST 是合法 IP 直接返回
    2. DNS 解析 BACKEND_PUBLIC_HOST 为 IP
    3. DNS 解析 STREAM_PUBLIC_HOST 为 IP
    4. 自动检测本机出口 IP
    5. 回退到 SIP_IP（排除 0.0.0.0）
    """
    global _sip_via_ip_cache
    if _sip_via_ip_cache:
        return _sip_via_ip_cache

    import socket as _socket

    def _is_ip(addr: str) -> bool:
        try:
            _socket.inet_aton(addr)
            return True
        except OSError:
            return False

    def _resolve(host: str) -> str | None:
        if not host or host == "localhost":
            return None
        if _is_ip(host):
            return host
        try:
            return _socket.gethostbyname(host)
        except (OSError, UnicodeError):
            return None

    # 依次尝试解析配置的域名
    for candidate in (settings.BACKEND_PUBLIC_HOST, settings.STREAM_PUBLIC_HOST):
        ip = _resolve(candidate or "")
        if ip:
            _sip_via_ip_cache = ip
            return ip

    # 回退：SIP_IP（排除 0.0.0.0）
    sip_ip = settings.SIP_IP or ""
    if sip_ip and sip_ip != "0.0.0.0" and _is_ip(sip_ip):
        _sip_via_ip_cache = sip_ip
        return sip_ip

    # 最后回退：自动检测本机出口 IP
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        detected = s.getsockname()[0]
        s.close()
        if detected:
            _sip_via_ip_cache = detected
            return detected
    except Exception as _detect_err:
        logger.debug(f"SIP VIA IP auto-detect failed: {_detect_err}")

    _sip_via_ip_cache = "127.0.0.1"
    return "127.0.0.1"


def sip_from_to_host() -> str:
    """返回用于 SIP From/To URI 的 host 部分。

    FIX [2026-07-29 P0]: EasyGBS 等非标准平台对 From/To URI host 使用 SIP_DOMAIN
    (行政区划码) 的 MESSAGE 请求返回 400 Bad Request。实测 EasyGBS 自己发送的
    REGISTER/MESSAGE 均使用 IP:port 作为 From URI host。

    当 SIP_FROM_TO_USE_IP=true (默认) 时，返回 sip_via_host() (IP 地址)。
    当 SIP_FROM_TO_USE_IP=false 时，返回 settings.SIP_DOMAIN (行政区划码，GB28181 标准)。
    """
    if settings.SIP_FROM_TO_USE_IP:
        return sip_via_host()
    return settings.SIP_DOMAIN
