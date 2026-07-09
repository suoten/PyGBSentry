# PyGBSentry 开源版深度分析报告 V2

**分析日期**: 2026-07-02  
**分析范围**: `editions/open-source` 全量源码（backend + frontend）  
**分析方式**: 静态代码审查，不修改源码  
**背景**: 上一轮报告（V1）的所有问题已修复，本轮为全新分析

---

## 〇、上一轮问题修复确认 ✅

| 上轮问题 | 状态 | 说明 |
|----------|------|------|
| 缺失 `app/sip/auth.py` | ✅ 已修复 | 完整的 DigestAuth 实现，含 nonce 签发/验证/签名校验 |
| 缺失 `app/db/base.py` | ✅ 已修复 | SQLAlchemy Base 类已就位 |
| 缺失 `app/db/model_registry.py` | ✅ 已修复 | 模型注册表已就位 |
| 模型目录严重不完整（仅3个文件） | ✅ 已修复 | 现有 33+ 个模型文件，覆盖所有核心实体 |
| CSP 策略 `unsafe-inline`/`unsafe-eval` | ✅ 已修复 | 已迁移到 nonce-based CSP |
| `v-html` XSS 风险 | ✅ 已修复 | 已添加 `sanitizeHtml()` 包装（DOMPurify） |
| TopBar.vue 用户名存入 localStorage | ✅ 已修复 | 已移除 |
| 登录接口用户枚举风险 | ✅ 已修复 | 统一错误消息："Incorrect username or password" |
| 生产环境配置自相矛盾 | ✅ 已修复 | 新增 `model_validator` 强制检查 + 弱密钥检测 + SQLite 生产阻止 |
| WebSocket JWT 泄露 | ✅ 已修复 | 短期一次性 ws-ticket 替代 URL 中的 JWT |
| 启动异常吞没 | ✅ 已修复 | 关键服务（SECRET_KEY 为空）直接 `SystemExit(1)` |

---

## 一、🔶 高危问题 (High)

### 1.1 设备密码明文存储 — 4个模型未加密

以下模型中 GB28181 设备/接入源的密码以明文形式存储在数据库中，未使用 `field_crypto` 加密：

| 文件 | 行号 | 字段 | 用途 |
|------|------|------|------|
| `models/access_source.py` | 34 | `password` | 外部流接入源（RTMP/RTSP/GB28181）密码 |
| `models/asset.py` | 49 | `password` | 下级 GB28181 设备注册密码 |
| `models/resource.py` | 62 | `password` | 通道级密码 |
| `models/platform.py` | 36 | `password` | 上级级联平台密码 |

**风险分析**：
- 数据库被拖库后，攻击者可获取所有设备的 SIP 注册密码
- 这些密码是 GB28181 Digest 认证的凭据，泄露后可伪造设备注册/信令
- 系统中已有 `field_crypto.py` 加密模块（`_derive_key` + AES），但上述模型未使用

**对比**：`User` 模型使用 `hashed_password`（哈希存储），`UserApiKey` 使用 `hashed_key`（HMAC-SHA256），安全意识在模型间不一致。

**建议**：在 `Asset`、`AccessSource`、`Resource`、`ParentPlatform` 的密码字段上添加 `@encrypted_field` 装饰器或使用 `field_crypto` 的加密/解密钩子。

### 1.2 媒体节点密钥明文存储

`models/media_node.py` 第53行：

```python
secret = Column(String(64), nullable=False)
```

ZLMediaKit API 的 `secret` 以明文存储。该密钥用于与 ZLMediaKit 的 API 通信，泄漏后攻击者可控制媒体服务器（拉流、推流、录制等）。

**说明**：虽然该值需要可逆（调用 ZLMediaKit API 时需要原始值），但应使用 `field_crypto` 加密存储，而非明文。

---

## 二、🟡 中危问题 (Medium)

### 2.1 DeviceSubscription 缺少 ForeignKey 约束

`models/device_subscription.py` 第29行：

```python
asset_id = Column(String(32), nullable=False, unique=True, index=True)
```

`asset_id` 引用了 `assets.id`，但**没有定义 `ForeignKey` 约束**。这意味着：
- 设备被删除后，其订阅记录成为孤儿数据
- 数据库层面无法保证引用完整性
- 与 `alarm_notification.py` 不同（该文件有注释说明故意使用软引用），`device_subscription.py` 无此说明

**对比**：`Alarm` 模型正确使用了 `ForeignKey("assets.gb_id")`，`Resource` 模型使用了 `ForeignKey("assets.id")`。

### 2.2 RecordSchedule 缺少 tenant_id 字段

`models/record_schedule.py` 整个模型缺少 `tenant_id` 字段，而其运行时表 `record_schedule_runtime.py` 第27行有：

```python
tenant_id = Column(String(64), default="default", index=True)
```

这意味着在多租户环境下：
- 录像计划无法按租户隔离查询
- 租户A可能看到/修改租户B的录像计划
- API 层需要额外在 `resource_id` 上做 JOIN 过滤来弥补，增加了 N+1 查询风险

**建议**：给 `RecordSchedule` 添加 `tenant_id` 字段，与 `RecordScheduleRuntime` 保持一致。

### 2.3 verify_token 端点存在用户枚举风险

`api/v1/endpoints/login.py` 第28-58行，`/login/verify-token` 端点：

```python
# 不同失败原因返回不同错误消息：
raise HTTPException(status_code=401, detail="Authentication token not provided")    # 无token
raise HTTPException(status_code=401, detail="Invalid or expired token")            # token无效
raise HTTPException(status_code=401, detail="User account is disabled")            # 用户被禁用
raise HTTPException(status_code=401, detail="Token verification failed")           # JWT解析失败
```

攻击者可以通过不同错误消息推断用户状态（存在/被禁用/已删除）。虽然这需要有效的或最近过期的 token，相比登录接口风险较低，但仍建议统一为通用错误消息。

**对比**：登录接口 `/login/access-token` 已正确使用统一错误消息 `"Incorrect username or password"`。

### 2.4 health/overview 端点权限控制过宽

`api/v1/endpoints/health.py` 第176-219行，`/overview` 端点：

```python
current_user: User = Depends(deps.get_current_active_user),
```

该端点仅要求**任意已认证用户**即可访问，但返回的数据包括：
- 设备总数、在线设备数
- 通道总数、在线通道数
- 在线率
- 录像记录数、录像完整率
- SIP 速率限制指标

这些运维指标通常应仅对管理员/运维人员可见。低权限用户（如 `viewer`）不应获取全局系统统计信息。

### 2.5 SIP Nonce 配置项未在 settings 中显式定义

`handlers.py` 第64行：

```python
_DIGEST_NONCE_TTL_SECONDS = int(getattr(settings, "SIP_DIGEST_NONCE_TTL_SECONDS", 300) or 300)
```

`SIP_DIGEST_NONCE_TTL_SECONDS` 和 `state_backend.py` 中的 `SIP_NONCE_NC_TTL_SECONDS` 均通过 `getattr` 动态读取，但 **未在 `config.py` 的 `Settings` 类中声明**。这导致：
- 配置项不可自动发现（IDE 无补全、文档无体现）
- 拼写错误不会被 Pydantic 捕获
- 运维人员不知道这些配置项存在

### 2.6 前后端配置默认值不一致

`config.py` 中 `SIP_NONCE_SECRET` 未声明（仅通过 `getattr` 读取），而 `auth.py` 和 `handlers.py` 中均需要此配置。如果运维人员未手动设置，`auth.py` 会回退使用 `SECRET_KEY`，这违背了密钥分离原则（上轮报告已指出 `field_crypto.py` 的类似问题）。

---

## 三、🟢 低危/改进建议 (Low/Improvement)

### 3.1 generate_uuid() 函数在 30+ 个模型文件中重复定义

每个模型文件（共 33+ 个）都包含相同的代码块：

```python
import uuid
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex
```

这违反了 DRY（Don't Repeat Yourself）原则，建议提取到 `app/db/base.py` 或 `app/utils/uuid.py` 中统一管理。

### 3.2 sanitize.ts 允许 style 属性 — 潜在 CSS 注入

`frontend/src/utils/sanitize.ts` 第17行：

```typescript
ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'style'],
```

`style` 属性在允许列表中。虽然 DOMPurify 会过滤 `expression()` 等危险 CSS 函数，但在某些旧浏览器中，CSS 仍可能被用于数据窃取（如 `background: url(...)` 外传数据）。建议移除 `style` 或限制为仅允许特定 CSS 属性。

### 3.3 localStorage 仍广泛使用

`localStorage` 在 7 个文件中使用 `setItem`，9 个文件中使用 `getItem`：

| 文件 | 存储内容 |
|------|---------|
| `App.vue` | `tenant_branding_cache` |
| `AdvancedVideoPlayerDialog.vue` | 播放器偏好 |
| `ChannelManager.vue` | 播放器偏好 |
| `MonitorCenter.vue` | 播放器偏好 |
| `Operations.vue` | 播放器偏好 |
| `AuditCenter.vue` | 播放器偏好 |
| `TvWall.vue` | 播放器偏好 |
| `locales/index.ts` | 语言设置 |

虽然这些数据不包含 token 或密码等敏感信息，但 `tenant_branding_cache` 可能包含租户配置信息。建议将 `tenant_branding_cache` 迁移到 `sessionStorage`。

### 3.4 SIP_ID 默认值仍为硬编码

`config.py` 中：

```python
SIP_ID: str = "34020000002000000001"
SIP_DOMAIN: str = "3402000000"
```

虽然启动时有警告日志，但默认值在信令层面仍可能导致多实例部署冲突。建议在 `model_validator` 中增加生产环境下的 SIP_ID 唯一性警告。

### 3.5 日志级别仍设置为 DEBUG

`main.py` 第217行：

```python
_root.setLevel(logging.DEBUG)
```

虽然 loguru 的 stderr sink 为 `INFO` 级别，但通过 `_LoguruLoggingHandler` 桥接后，第三方库（如 SQLAlchemy、aiosip）的 DEBUG 日志也会被转发。在生产环境中建议设置为 `WARNING` 或 `INFO`。

### 3.6 测试覆盖仍然不足

`tests/` 目录中测试文件数量有限，缺少：
- SIP 协议一致性测试
- 并发/竞态条件测试
- 安全渗透测试
- 多租户数据隔离测试

---

## 四、📊 架构层面建议

### 4.1 密码存储策略不统一

当前系统存在三种密码存储方式：

| 方式 | 适用模型 | 安全性 |
|------|---------|--------|
| 哈希（不可逆） | `User.hashed_password` | 高 — 无法还原 |
| HMAC-SHA256 | `UserApiKey.hashed_key` | 高 — 仅存储验证用摘要 |
| 明文 | `Asset.password`, `AccessSource.password`, `Resource.password`, `Platform.password`, `MediaNode.secret` | 低 — 拖库即泄露 |

应统一使用 `field_crypto` 对需要可逆的密码进行加密存储，对不需要可逆的密码使用哈希存储。

### 4.2 模型 design consistency 不一致

不同模型在以下方面存在不一致：
- `tenant_id` 字段：大部分模型有，但 `RecordSchedule` 缺失
- `ForeignKey` 约束：`Alarm`、`Resource` 有，`DeviceSubscription`、`AlarmNotification` 无
- `created_at`/`updated_at`：大部分有，但命名不统一（有的用 `time`，有的用 `created_at`）
- `index=True`：部分模型在 `tenant_id` 上有索引，部分没有

建议制定模型设计规范文档，统一字段命名、约束和索引策略。

### 4.3 配置项可发现性

当前系统有大量配置项通过 `getattr(settings, "KEY", default)` 动态读取（如 `SIP_DIGEST_NONCE_TTL_SECONDS`、`SIP_NONCE_NC_TTL_SECONDS`、`SIP_NONCE_SECRET`），这些配置项未在 `config.py` 的 `Settings` 类中声明，导致：
- 运维人员无法通过查看 `config.py` 了解所有配置项
- 拼写错误不会被 Pydantic 捕获
- IDE 无自动补全

建议在 `Settings` 类中显式声明所有配置项，即使是可选的。

---

## 五、📋 问题优先级汇总

| 优先级 | 数量 | 关键问题 |
|--------|------|---------|
| 🔶 High | 2 | 4个模型密码明文存储；媒体节点密钥明文存储 |
| 🟡 Medium | 10 | DeviceSubscription 缺 FK；RecordSchedule 缺 tenant_id；verify_token 用户枚举；health/overview 权限过宽；SIP 配置项未声明；SIP_NONCE_SECRET 回退；_cleanup_locks 内存泄漏；_SEEN_REQUESTS 无锁并发；_auth_failure_tracker 未清理；ZLM secret 通过 URL 参数传递 |
| 🟢 Low | 6 | generate_uuid 重复定义；sanitize 允许 style；localStorage 仍广泛使用；SIP_ID 硬编码；日志 DEBUG 级别；测试覆盖不足 |

---

### 2.7 _cleanup_locks 字典无限增长 — 内存泄漏

`handlers.py` 第75-85行：

```python
_cleanup_locks: dict[str, asyncio.Lock] = {}
_cleanup_locks_guard = asyncio.Lock()

async def _get_cleanup_lock(gb_id: str) -> asyncio.Lock:
    async with _cleanup_locks_guard:
        lock = _cleanup_locks.get(gb_id)
        if lock is None:
            lock = asyncio.Lock()
            _cleanup_locks[gb_id] = lock
        return lock
```

每个设备下线时都会创建一个 per-gb_id 的 `asyncio.Lock`，但**从未清理**。在有大量设备频繁上线的场景下，`_cleanup_locks` 字典会无限增长，每个无效条目占用约 200-300 字节。对于 10,000+ 设备的部署，这可能导致内存泄漏。

**建议**：在设备清理完成后将对应的 lock 从字典中移除，或使用 `weakref` / `LRU` 缓存。

### 2.8 _SEEN_REQUESTS 全局字典无锁并发访问

`server.py` 第661-679行，`handlers.py` 第69行：

```python
# handlers.py - 全局状态
_SEEN_REQUESTS: dict[str, float] = {}

# server.py - 无锁访问
if dedup_key in _SEEN_REQUESTS and msg.method not in ("INVITE",):
    ...
_SEEN_REQUESTS[dedup_key] = now
...
_SEEN_REQUESTS.pop(k, None)
```

`_SEEN_REQUESTS` 是一个全局字典，被多个异步协程并发读写，**没有任何锁保护**。虽然 Python 的 GIL 保证了单个字节码操作的原子性，但 `dict` 的复合操作（`in` + `[]` + `pop`）不是原子的。在高并发 SIP 消息处理下，可能导致：
- 竞态条件下漏检重复请求
- `RuntimeError: dictionary changed size during iteration`（虽然代码已用 `list()` 快照，但快照与实际 pop 之间窗口仍然存在）

**建议**：使用 `asyncio.Lock` 保护 `_SEEN_REQUESTS` 的读写，或改用 `contextvars` / 线程安全的数据结构。

### 2.9 _auth_failure_tracker 未定期清理过期条目

`state_backend.py` 第45-47行：

```python
self._auth_failure_tracker: dict[str, list[float]] = {}
self._auth_failure_ttl = 300
self._auth_failure_max_size = 5000
```

`_auth_failure_tracker` 记录了每个 IP 的鉴权失败时间戳列表，用于自动黑名单。但只定义了 `_auth_failure_ttl` 和 `_auth_failure_max_size`，**没有定期清理过期条目**的逻辑。与 `_SEEN_REQUESTS` 不同，这里没有在大小超限时触发清理。如果攻击者使用大量不同 IP 进行暴力破解，字典会持续增长至 `_auth_failure_max_size`。

**建议**：在 `record_auth_failure` 方法中添加过期条目清理逻辑，或使用定时任务周期性清理。

### 2.10 ZLMediaKit API secret 通过 URL 查询参数传递

`media_nodes.py` 第102-104行：

```python
url = f"http://{node['host']}:{node['http_port']}/index/api/getMediaList"
r = await client.get(url, params={"secret": _zlm_secret(node)}, timeout=2.0)
```

ZLMediaKit 的 API `secret` 通过 HTTP GET 请求的 URL 查询参数传递。虽然 ZLMediaKit 的 API 设计如此，但：
- URL 参数会被记录在 HTTP 代理/反向代理日志中
- 如果 ZLMediaKit 部署在非本地网络，secret 可能被中间人截获
- 建议 ZLMediaKit 侧支持 Header 认证（如 `X-Secret` 头），或至少使用 POST body 传递

---

## 六、总结

相比上一轮分析，PyGBSentry 开源版在以下方面取得了显著进步：

1. **源码完整性** ✅ — 所有缺失的核心源文件已补齐，项目可正常启动
2. **安全加固** ✅ — CSP 升级为 nonce-based、v-html 添加 DOMPurify、WebSocket 改用短期 ticket、登录接口统一错误消息、生产环境强制检查（弱密钥/Redis/SQLite）
3. **代码质量** ✅ — 模型目录完整、配置校验增强

**剩余的核心问题集中在密码存储安全**：5 个模型（Asset、AccessSource、Resource、ParentPlatform、MediaNode）仍以明文存储密码/密钥。这是当前最需要优先解决的问题，因为系统已有 `field_crypto` 加密基础设施，接入成本低但安全收益大。

**建议修复顺序**：
1. 🔶 对 4 个设备密码字段 + 1 个媒体密钥字段添加 `field_crypto` 加密
2. 🟡 给 `RecordSchedule` 添加 `tenant_id` 字段
3. 🟡 给 `DeviceSubscription.asset_id` 添加 `ForeignKey` 约束
4. 🟡 在 `config.py` 中显式声明所有 SIP 配置项
5. 🟡 给 `_cleanup_locks` 字典添加清理逻辑（防止内存泄漏）
6. 🟡 给 `_SEEN_REQUESTS` 添加 asyncio.Lock 保护（防止竞态条件）
7. 🟡 给 `_auth_failure_tracker` 添加过期清理逻辑
8. 🟢 提取公共 `generate_uuid()` 到统一模块
9. 🟢 收紧 `health/overview` 端点权限