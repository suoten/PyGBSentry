# PyGBSentry 问题修复提示语集

> 本文档基于 `DEEP_ANALYSIS_REPORT_V3.md` 生成,包含针对每个问题的结构化修复提示语。  
> 可直接复制对应提示语到 AI 编码助手(如 CatPaw / Cursor / Copilot)中执行修复。  
> **项目根目录**: `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source`  
> **技术栈**: Python FastAPI + Vue3 + PostgreSQL + Redis + ZLMediaKit

---

## 使用说明

1. 按优先级从 P0 → P1 → P2 → P3 顺序执行
2. 每个提示语包含: 上下文背景、目标文件、具体要求、验收标准
3. 建议每次只执行一个提示语,修复完成后运行测试再进行下一项
4. 提示语中 `{项目根目录}` 指代 `editions/open-source`

---

## 一、🔴 P0 致命问题提示语

### PROMPT-P0-01: 加密设备密码字段

```
你是一个高级 Python 后端安全工程师。请在 PyGBSentry 项目中修复设备密码明文存储的安全漏洞。

## 背景
项目中以下 4 个模型的 password 字段以明文存储在数据库中,存在严重安全隐患:
- backend/app/models/access_source.py (外部流接入源密码)
- backend/app/models/asset.py (GB28181设备注册密码)
- backend/app/models/resource.py (通道级密码)
- backend/app/models/platform.py (上级级联平台密码)

项目中已有加密模块 backend/app/core/field_crypto.py,但上述模型未使用。

## 要求
1. 先阅读 backend/app/core/field_crypto.py 了解现有加密方案的 API
2. 阅读上述 4 个模型文件,了解 password 字段的定义和使用方式
3. 全局搜索所有读取/写入这些 password 字段的位置(grep "asset.password" "\.password" 等)
4. 使用 field_crypto 对 4 个模型的 password 字段实现透明加解密
5. 编写 Alembic 数据迁移脚本,将现有明文密码加密迁移
6. 确保所有读取密码的地方(如 SIP Digest 认证)能正确获取解密后的明文
7. 确保所有写入密码的地方(如设备创建/更新 API)自动加密存储

## 约束
- 不能破坏现有 SIP Digest 认证流程
- 加密方案必须可逆(设备密码需要明文参与 Digest 计算)
- 迁移脚本需兼容 SQLite 和 PostgreSQL
- 迁移脚本需幂等(可重复执行不报错)

## 验收标准
- 4 个模型的 password 字段在数据库中存储为密文
- 设备注册/认证流程正常工作
- 现有测试全部通过
- 新增的数据迁移脚本可正确迁移已有数据
```

---

### PROMPT-P0-02: 加密媒体节点密钥

```
你是一个高级 Python 后端安全工程师。请在 PyGBSentry 项目中修复媒体节点密钥明文存储问题。

## 背景
backend/app/models/media_node.py 中的 secret 字段(ZLMediaKit API 密钥)以明文存储。
该密钥用于控制媒体服务器,泄露后可被完全控制。

## 要求
1. 阅读 backend/app/models/media_node.py 了解 secret 字段定义
2. 阅读 backend/app/core/field_crypto.py 了解加密方案
3. 全局搜索所有读取 media_node.secret 的位置
4. 对 secret 字段实现透明加解密(与 P0-01 相同的方案)
5. 确保所有 ZLM API 调用处能正确获取解密后的 secret
6. 编写 Alembic 迁移脚本加密现有数据
7. 确保 backend/app/main.py 中启动时的 SECRET 一致性校验仍然有效

## 验收标准
- secret 字段在数据库中存储为密文
- ZLM API 调用正常工作
- 启动时密钥一致性校验不受影响
- 现有测试全部通过
```

---

### PROMPT-P0-03: 修复 ZLM API 密钥传递方式

```
你是一个高级 Python 后端安全工程师。请在 PyGBSentry 项目中修复 ZLMediaKit API 密钥通过 URL 查询参数传递的安全问题。

## 背景
backend/app/core/media_nodes.py 中,调用 ZLMediaKit API 时将 secret 作为 URL 查询参数传递:
    r = await client.get(url, params={"secret": _zlm_secret(node)}, timeout=2.0)
这会导致 secret 出现在代理日志、访问日志中,存在泄露风险。

## 要求
1. 全局搜索所有向 ZLMediaKit 发送 API 请求的位置(grep "secret" "getMediaList" "index/api" 等)
2. 将所有 GET 请求中 params={"secret": ...} 改为通过 HTTP Header 传递:
   headers = {"X-Secret": secret_value}
   或对于必须用 GET 的接口,改为 POST 请求体传递
3. 检查 backend/app/services/zlm_rtp_server_service.py、zlm_stream_control.py 等所有 ZLM 相关服务
4. 确保修改后所有 ZLM API 调用仍然正常工作
5. 如果 ZLMediaKit 不支持 Header 认证,在代码中添加注释说明原因,并改为至少不在日志中记录 URL

## 约束
- 不能影响 ZLMediaKit API 的功能
- 需要兼容不同版本的 ZLMediaKit

## 验收标准
- 所有 ZLM API 调用不再通过 URL 查询参数传递 secret
- 日志中不出现 secret 明文
- ZLM 相关功能(拉流、推流、录制)正常工作
```

---

### PROMPT-P0-04: 升级 Docker 镜像版本

```
你是一个 DevOps 工程师。请在 PyGBSentry 项目中升级过旧的 Docker 镜像版本。

## 背景
docker-compose.yml 中使用了过旧的镜像版本:
- postgres:14-alpine (存在已知 CVE)
- redis:6-alpine (存在已知 CVE)

## 要求
1. 阅读 docker-compose.yml 和 docker-compose.ha.yml
2. 将 postgres:14-alpine 升级为 postgres:16-alpine
3. 将 redis:6-alpine 升级为 redis:7-alpine
4. 检查 docker-compose.monitoring.yml 中的镜像版本一并升级
5. 检查 deploy/helm/pygbsentry/ 中的镜像引用,如有过旧版本一并更新
6. 检查 backend/Dockerfile 和 frontend/Dockerfile 中的基础镜像版本
7. 确认升级后 healthcheck 配置仍然兼容

## 验收标准
- 所有 Docker 镜像使用最新稳定版
- docker-compose config 验证无错误
- 版本升级在注释中说明原因
```

---

### PROMPT-P0-05: 修复全局字典内存泄漏和竞态条件

```
你是一个高级 Python 异步编程工程师。请在 PyGBSentry 项目中修复全局字典内存泄漏和竞态条件问题。

## 背景
以下全局字典缺乏定期清理机制和并发保护,在高并发场景下会导致内存泄漏和数据竞争:

1. backend/app/sip/server.py — _SEEN_REQUESTS 字典(请求去重)
   - 被多个异步协程并发读写,无锁保护
   - 从未清理过期条目

2. backend/app/sip/state_backend.py — _auth_failure_tracker 字典(鉴权失败记录)
   - 定义了 _auth_failure_ttl 和 _auth_failure_max_size,但未实现清理逻辑

3. backend/app/sip/dialog_manager.py — _cleanup_locks 字典(清理锁)
   - 设备下线后创建的 per-gb_id 锁从未被清理

## 要求
1. 对 _SEEN_REQUESTS:
   - 添加 asyncio.Lock 保护并发读写
   - 添加定期清理机制(每 60 秒清理超过 60 秒的条目)
   - 在 SipServer 中启动一个后台 cleanup task

2. 对 _auth_failure_tracker:
   - 在 record_auth_failure 方法中实现过期条目清理
   - 当字典大小超过 _auth_failure_max_size 时触发清理
   - 添加 asyncio.Lock 保护并发访问

3. 对 _cleanup_locks:
   - 在设备清理完成的回调中,将对应的 lock 从字典中移除
   - 或使用 weakref 弱引用,使锁可被 GC 自动回收

## 约束
- 清理逻辑不能阻塞 SIP 消息处理主路径(用 fire_and_forget 或后台 task)
- 锁的粒度要合理,避免过度锁竞争影响性能
- 清理周期可配置(通过 settings)

## 验收标准
- 所有全局字典有定期清理机制
- 并发访问有锁保护
- 新增的后台清理 task 在应用关闭时正确取消
- 运行现有并发测试通过
```

---

## 二、🔶 P1 高危问题提示语

### PROMPT-P1-01: 前端 localStorage 迁移

```
你是一个前端安全工程师。请在 PyGBSentry 前端项目中修复 localStorage 滥用问题。

## 背景
前端有 20+ 处使用 localStorage 存储用户名、租户配置等敏感信息,暴露于 XSS 攻击。
JWT token 已迁移到 sessionStorage,但其他敏感信息仍在 localStorage 中。

## 要求
1. 全局搜索 frontend/src/ 下所有 localStorage 使用点
2. 分类整理: 哪些是敏感信息(用户名、token、租户配置),哪些是非敏感信息(语言偏好、播放器设置)
3. 将敏感信息迁移到 sessionStorage
4. 非敏感信息可保留在 localStorage,但需添加注释说明
5. 确保 Pinia store 中的用户状态不从 localStorage 读取敏感信息
6. 检查 frontend/src/stores/ 下的所有 store,确保持久化逻辑安全

## 验收标准
- 用户名、token 等敏感信息不再存储在 localStorage
- 登录/登出流程正常
- 页面刷新后用户状态正确恢复
- 前端现有测试通过
```

---

### PROMPT-P1-02: 收紧 CSP 策略

```
你是一个 Web 安全工程师。请在 PyGBSentry 项目中收紧 Content-Security-Policy 策略。

## 背景
backend/app/main.py 第 1145-1156 行,CSP 的 connect-src 策略过于宽松:
    "connect-src 'self' http: https: ws: wss:;"
允许连接任意 HTTP/HTTPS/WS/WSS 资源。

## 要求
1. 阅读 backend/app/main.py 中 SecurityHeadersMiddleware 的 CSP 配置
2. 阅读 backend/app/core/config.py 中 CSP 相关配置项
3. 将 connect-src 收紧为仅允许 'self' 和配置的白名单域名
4. 添加新的配置项 CSP_CONNECT_SRC_DOMAINS(逗号分隔的域名列表)
5. 确保 WebSocket 连接(SIP trace、日志推送)不受影响
6. 确保 ZLMediaKit 的流媒体连接不受影响
7. 确保地图服务(天地图、高德、百度地图)的 tile 请求不受影响

## 验收标准
- CSP connect-src 不再包含通配的 http:/https:/ws:/wss:
- 仅允许 'self' 和配置的白名单域名
- 所有前端功能(播放、WebSocket、地图)正常工作
- 浏览器控制台无 CSP 违规报告
```

---

### PROMPT-P1-03: 实现登录失败次数限制

```
你是一个后端安全工程师。请在 PyGBSentry 项目中实现登录失败次数限制和账户锁定机制。

## 背景
backend/app/api/v1/endpoints/login.py 中登录接口未实现失败次数限制,存在暴力破解风险。
项目中已有 slowapi 依赖(requirements.txt 中),可用于限流。

## 要求
1. 阅读 backend/app/api/v1/endpoints/login.py 了解登录流程
2. 阅读 backend/app/core/ratelimit.py 了解现有限流配置
3. 实现 IP 级限流: 同一 IP 5分钟内最多 10 次登录请求
4. 在 backend/app/models/user.py 中添加字段:
   - failed_login_attempts: Integer, default=0
   - locked_until: DateTime, nullable=True
5. 实现账户锁定逻辑:
   - 连续失败 5 次锁定 30 分钟
   - 锁定期间拒绝登录并返回 423 Locked
   - 锁定期满自动解锁,重置失败计数
   - 登录成功时重置失败计数
6. 编写 Alembic 迁移脚本添加新字段
7. 在登录 API 中集成限流和锁定检查
8. 添加审计日志记录锁定/解锁事件

## 验收标准
- 暴力破解登录会被限流(429)和锁定(423)
- 正常用户登录不受影响
- 锁定/解锁有审计日志
- 新增单元测试覆盖限流和锁定逻辑
```

---

### PROMPT-P1-04: 添加密码强度验证

```
你是一个后端安全工程师。请在 PyGBSentry 项目中添加密码强度验证。

## 背景
用户创建/修改密码时,未验证密码强度(长度、复杂度),允许弱密码。

## 要求
1. 在 backend/app/core/security.py 中添加 validate_password_strength 函数:
   - 最少 8 个字符
   - 必须包含大写字母
   - 必须包含小写字母
   - 必须包含数字
   - 必须包含特殊字符
   - 返回 (bool, str) 元组,第二个元素为错误消息
2. 搜索所有设置/修改密码的 API 端点(grep "password" "create_user" "change_password" "reset_password")
3. 在所有密码设置入口调用 validate_password_strength
4. 密码不满足要求时返回 400 Bad Request
5. 支持通过配置开关控制是否强制密码强度(ENABLE_PASSWORD_STRENGTH_CHECK)
6. 错误消息支持 i18n(根据 APP_LANGUAGE 返回中英文)

## 验收标准
- 弱密码被拒绝
- 强密码通过
- 错误消息清晰且国际化
- 配置开关可关闭检查(开发环境)
```

---

### PROMPT-P1-05: 修复异常静默吞没

```
你是一个高级 Python 工程师。请在 PyGBSentry 项目中修复异常静默吞没问题。

## 背景
项目中有 58+ 处 `except ...: pass` 语句,异常被完全吞没,生产问题无法追踪。
参考 system_check_report.md 和 system_check_report_v2.md 中的完整列表。

## 要求
1. 阅读 system_check_report_v2.md 获取所有异常吞没的位置列表
2. 逐个审查每个 `except ...: pass`:
   - 非关键路径: 至少添加 logger.warning 或 logger.debug 记录异常
   - 关键路径(启动、认证、数据库操作): 记录日志后 re-raise
   - 确实需要忽略的异常(如 CancelledError): 添加注释说明原因
3. 优先修复 P0 级别的异常吞没(标注为 P0 的位置)
4. 然后修复 P1/P2 级别的异常吞没
5. P3 级别的可暂缓,但需添加 TODO 注释

## 分批执行
由于修改点较多,建议分批处理:
- 第1批: backend/app/main.py (3处)
- 第2批: backend/app/core/ 目录 (plugin_manager.py 3处, ratelimit.py 1处, redis.py 2处)
- 第3批: backend/app/sip/ 目录 (handlers.py 2处, dialog_manager.py 2处, catalog_runtime.py 1处)
- 第4批: backend/app/api/v1/endpoints/ 目录
- 第5批: backend/app/services/ 目录

## 验收标准
- 不再有 `except ...: pass` 无注释的代码
- 所有异常至少有日志记录
- 关键路径异常会 re-raise
- 现有测试全部通过
```

---

### PROMPT-P1-06: 配置 SSL/TLS 强制要求

```
你是一个 DevOps 安全工程师。请在 PyGBSentry 项目中强制生产环境使用 HTTPS。

## 背景
生产环境部署默认使用 HTTP,所有通信明文传输,违反等保2.0要求。
项目中已有 SSL Certbot 模块(backend/app/services/ssl_certbot/),但未强制启用。

## 要求
1. 在 backend/app/core/config.py 中添加配置项:
   - FORCE_HTTPS_IN_PRODUCTION: bool = True (生产环境强制 HTTPS)
2. 在 backend/app/main.py 中添加中间件:
   - 当 APP_ENV=prod 且 FORCE_HTTPS_IN_PRODUCTION=true 时
   - 检查请求是否通过 HTTPS(检查 X-Forwarded-Proto 头)
   - 非 HTTPS 请求返回 301 重定向到 HTTPS
3. 更新 deploy/nginx/ 中的 Nginx 配置,提供 HTTPS 示例配置
4. 更新 docker-compose.yml,添加 443 端口映射和 SSL 卷
5. 更新 docs/deployment.md,在部署步骤中强制要求配置 HTTPS
6. 在部署检查清单中添加 HTTPS 配置检查项

## 验收标准
- 生产环境 HTTP 请求自动重定向到 HTTPS
- 开发环境不受影响
- 部署文档中明确要求 HTTPS
- Nginx 配置示例包含 SSL 设置
```

---

### PROMPT-P1-07: 优化数据库连接池配置

```
你是一个数据库性能优化工程师。请在 PyGBSentry 项目中优化数据库连接池配置。

## 背景
backend/app/db/session.py 中默认连接池配置(pool_size=20, max_overflow=50)在高并发场景下可能不足。
且 SQLite 使用了不合理的 pool_size/max_overflow 参数。

## 要求
1. 阅读 backend/app/db/session.py 了解当前配置
2. 阅读 backend/app/core/config.py 中 DB_POOL_SIZE、DB_MAX_OVERFLOW、DB_POOL_RECYCLE 的默认值
3. 为 SQLite 和非 SQLite 分别优化默认值:
   - SQLite: pool_size=5, max_overflow=10 (SQLite 不支持高并发)
   - PostgreSQL/MySQL: pool_size=30, max_overflow=20 (生产推荐)
4. 添加连接池监控: 在 health_service 中添加连接池使用率检查
5. 当连接池使用率超过 80% 时记录 WARNING 日志
6. 在 /metrics 端点暴露连接池指标(使用 prometheus_client)
7. 更新 .env.example 中的推荐配置值和注释

## 验收标准
- SQLite 和非 SQLite 使用不同的默认连接池参数
- 连接池使用率可监控
- 高使用率时有告警日志
- Prometheus 指标包含连接池信息
```

---

### PROMPT-P1-08: 添加登录审计日志

```
你是一个安全审计工程师。请在 PyGBSentry 项目中完善登录审计日志。

## 背景
虽然项目有 auth_audit 服务,但登录成功/失败的审计记录不够完整。

## 要求
1. 阅读 backend/app/services/auth_audit.py 了解现有审计逻辑
2. 阅读 backend/app/api/v1/endpoints/login.py 了解登录流程
3. 确保以下事件都有审计记录:
   - 登录成功(记录用户名、IP、User-Agent、时间)
   - 登录失败(记录尝试的用户名、IP、失败原因)
   - 账户锁定(记录用户名、IP、锁定时长)
   - 账户解锁(记录用户名、解锁方式: 自动/手动)
   - Token 刷新成功/失败
   - 退出登录
4. 审计日志写入 operation_audit 表(已有模型)
5. 敏感信息(密码)不得出现在日志中
6. 审计日志支持按时间范围、用户名、事件类型查询
7. 添加 API 端点供管理员查看审计日志

## 验收标准
- 所有认证相关事件有审计记录
- 审计日志不含敏感信息
- 管理员可查询审计日志
- 审计日志有哈希链保护(利用现有 HashChainSink)
```

---

## 三、🟡 P2 中危问题提示语

### PROMPT-P2-01: 添加 ForeignKey 级联删除

```
你是一个数据库工程师。请在 PyGBSentry 项目中为 DeviceSubscription 添加 ForeignKey 约束。

## 背景
backend/app/models/device_subscription.py 中 device_id 字段缺少 ForeignKey 约束,
设备删除后订阅记录仍存在,导致数据不一致。

## 要求
1. 阅读 backend/app/models/device_subscription.py
2. 阅读 backend/app/models/asset.py 了解主键定义
3. 为 device_id 添加 ForeignKey("assets.id", ondelete="CASCADE")
4. 检查其他模型是否有类似的外键缺失问题(grep "Column(String.*index=True" 但无 ForeignKey)
5. 编写 Alembic 迁移脚本添加外键约束
6. 迁移脚本需先清理孤立的订阅记录(引用了已删除设备的记录)

## 验收标准
- 设备删除时自动删除关联的订阅记录
- 迁移脚本兼容 SQLite 和 PostgreSQL
- 孤立记录被清理
```

---

### PROMPT-P2-02: 强制生产环境 SIP 状态后端为 Redis

```
你是一个后端工程师。请在 PyGBSentry 项目中强制生产环境使用 Redis 作为 SIP 状态后端。

## 背景
backend/app/sip/state_backend.py 中 SIP_STATE_BACKEND=local 时,生产环境仅告警不阻止启动。
这会导致多实例部署时 Nonce/NC 重放检查和 INVITE 限流不共享,存在安全风险。

## 要求
1. 在 backend/app/core/config.py 的 model_validator 中添加检查:
   - 当 APP_ENV in {"prod", "production"} 且 SIP_STATE_BACKEND == "local" 时
   - 抛出 ValueError 拒绝启动
2. 错误消息说明原因和修复方法
3. 更新 .env.example 中的注释说明
4. 添加单元测试验证生产环境拒绝 local 后端

## 验收标准
- 生产环境使用 local 后端时拒绝启动
- 开发环境不受影响
- 错误消息清晰
```

---

### PROMPT-P2-03: 添加慢查询监控

```
你是一个数据库性能工程师。请在 PyGBSentry 项目中添加慢查询监控。

## 背景
项目未集成慢查询监控,无法及时发现数据库性能退化。

## 要求
1. 在 backend/app/db/session.py 中添加 SQLAlchemy event 监听器:
   - before_cursor_execute: 记录查询开始时间
   - after_cursor_execute: 计算耗时,超过阈值(默认 1 秒)记录 WARNING
2. 添加配置项 SLOW_QUERY_THRESHOLD_SECONDS: float = 1.0
3. 在 /metrics 端点暴露慢查询计数(按表名/操作类型分类)
4. 在 health_service 的周期检查中统计慢查询频率
5. 慢查询频率过高时触发告警

## 验收标准
- 慢查询被记录到日志
- Prometheus 指标包含慢查询计数
- 阈值可配置
- 不影响正常查询性能(event 监听器开销极小)
```

---

### PROMPT-P2-04: 添加前端错误边界

```
你是一个前端工程师。请在 PyGBSentry 前端项目中添加全局错误边界。

## 背景
Vue3 应用未实现全局错误边界,组件错误可能导致整个应用白屏。

## 要求
1. 创建 frontend/src/components/common/ErrorBoundary.vue:
   - 使用 onErrorCaptured 捕获子组件错误
   - 显示友好的错误提示页面(而不是白屏)
   - 提供"重新加载"和"返回首页"按钮
2. 在 frontend/src/App.vue 中使用 ErrorBoundary 包裹 router-view
3. 错误发生时上报到后端 /api/v1/logs/error 端点(如已有)或记录到本地
4. 错误页面样式与项目整体风格一致(使用 Element Plus 组件)
5. 支持开发模式显示详细错误堆栈,生产模式显示简化信息

## 验收标准
- 组件抛出异常时显示错误页面而非白屏
- 用户可以重新加载或返回首页
- 开发模式显示错误堆栈
- 生产模式不暴露敏感信息
```

---

### PROMPT-P2-05: 插件沙箱安全加固

```
你是一个安全工程师。请在 PyGBSentry 项目中加固插件沙箱安全性。

## 背景
backend/app/core/plugin_manager.py 中的插件沙箱通过 sys.meta_path 拦截 import,
但存在潜在的绕过方式(反射加载、别名等)。

## 要求
1. 阅读 backend/app/core/plugin_manager.py 中沙箱相关代码
   (_PLUGIN_SANDBOX_BLOCKED_MODULES, _PluginSandboxImportHook, _install_plugin_sandbox_*)
2. 审查以下绕过风险:
   - 通过 type().__subclasses__() 绕过
   - 通过 __builtins__ 反射绕过
   - 通过已信任模块(如 importlib)的内部方法绕过
   - 通过 ctypes/cffi 的 C 级别调用绕过
3. 增强沙箱防护:
   - 扩展 _PLUGIN_SANDBOX_BLOCKED_MODULES 黑名单
   - 添加对 __builtins__ 的保护(限制 __import__ 的访问)
   - 添加沙箱逃逸检测日志
4. 编写测试验证沙箱防护有效性(test_malicious_plugin_interception.py 中补充用例)
5. 在文档中说明沙箱的限制和推荐的安全部署方式(进程级隔离)

## 验收标准
- 常见的沙箱绕过方式被阻止
- 绕过尝试被记录到日志
- 恶意插件拦截测试通过
- 文档说明沙箱局限性
```

---

### PROMPT-P2-06: 实现 API 版本弃用策略

```
你是一个 API 设计工程师。请在 PyGBSentry 项目中完善 API 版本弃用策略。

## 背景
backend/app/api/versioning.py 中已有 API 版本中间件,但缺少弃用策略和 Sunset 响应头。

## 要求
1. 阅读 backend/app/api/versioning.py 了解现有版本中间件
2. 定义 API 版本生命周期配置:
   - stable: 正常可用
   - deprecated: 仍可用但添加 Deprecation/Sunset 头
   - sunset: 已下线,返回 410 Gone
3. 在版本中间件中,对已弃用版本的请求添加响应头:
   - Deprecation: true
   - Sunset: <ISO 8601 日期>
   - Link: </api/v2/...>; rel="successor-version"
4. 在 OpenAPI 文档中标注已弃用的端点
5. 添加配置项控制当前活跃版本和弃用版本

## 验收标准
- 已弃用版本返回正确的响应头
- 客户端可从响应头获取新版本端点地址
- OpenAPI 文档正确标注弃用状态
```

---

### PROMPT-P2-07: 修复数据库会话并发问题

```
你是一个高级 Python 异步编程工程师。请在 PyGBSentry 项目中全面修复数据库会话并发问题。

## 背景
backend/tests/test_session_concurrency_bug.py 中记录了已知的并发问题:
- asyncio.gather 使用同一个 AsyncSession 导致 "Method 'close()' can't be called here"
- 连接池泄漏

stream_session_service.py 已部分修复,但需要全面审查其他并发场景。

## 要求
1. 阅读 backend/tests/test_session_concurrency_bug.py 了解已知问题
2. 阅读 backend/app/services/stream_session_service.py 了解已有的修复模式
3. 全局搜索 asyncio.gather 的使用点(grep "asyncio.gather" backend/app/)
4. 审查每个 asyncio.gather 是否共享了同一个 AsyncSession:
   - 如果共享: 改为每个并发任务创建独立的 session
   - 或改为顺序执行(如果任务间有依赖)
5. 检查 asyncio.create_task 的使用,确保不会在多个 task 间共享 session
6. 在 backend/app/db/session.py 中添加调试模式下的 session 泄漏检测

## 验收标准
- 不再有多个协程共享同一个 AsyncSession 的情况
- 高并发下不出现 "Method 'close()' can't be called here" 错误
- 连接池使用率正常(无泄漏)
- 并发测试通过
```

---

## 四、🟢 P3 低危/建议提示语

### PROMPT-P3-01: 消除硬编码配置

```
你是一个代码质量工程师。请在 PyGBSentry 项目中将硬编码配置迁移到 settings。

## 背景
项目中有 189 处硬编码的配置值(超时时间、端口范围、阈值等)。

## 要求
1. 参考 system_check_report_v2.md 中的硬编码列表
2. 将以下类别的硬编码值迁移到 backend/app/core/config.py:
   - 超时时间(如 timeout=2.0 → timeout=settings.ZLM_REQUEST_TIMEOUT_SHORT)
   - 端口和地址
   - 容量限制(如 maxsize=10000 → maxsize=settings.SIP_TASK_QUEUE_SIZE)
   - 时间间隔(如 60 秒清理周期)
3. 每批处理 20-30 个,避免一次修改过多
4. 为新增的配置项添加合理的默认值和注释
5. 更新 .env.example

## 验收标准
- 硬编码数量减少 80%+
- 所有配置项有默认值
- .env.example 包含新增配置项
```

---

### PROMPT-P3-02: 消除魔法数字

```
你是一个代码质量工程师。请在 PyGBSentry 项目中消除魔法数字。

## 背景
代码中存在大量无注释的魔法数字,影响可读性和可维护性。

## 要求
1. 全局搜索常见的魔法数字模式(如 `if x >= 10000`, `timeout=30` 等)
2. 将魔法数字提取为命名常量或配置项:
   - 文件内的常量: 在文件顶部定义 UPPER_SNAKE_CASE 常量
   - 跨文件共享的: 迁移到 config.py
3. 为每个常量添加注释说明含义
4. 优先处理 backend/app/sip/ 和 backend/app/services/ 目录

## 验收标准
- 代码中不再有未注释的魔法数字
- 常量命名清晰
- 现有功能不受影响
```

---

### PROMPT-P3-03: 锁定依赖版本

```
你是一个 DevOps 工程师。请在 PyGBSentry 项目中锁定依赖版本。

## 背景
requirements.txt 中部分依赖未指定精确版本,可能导致不同环境构建结果不一致。

## 要求
1. 运行 pip freeze 生成精确的依赖锁定文件
2. 创建 requirements-lock.txt 包含所有传递依赖的精确版本
3. 在 requirements.txt 中为所有依赖指定精确版本(使用 ==)
4. 检查并更新已知的漏洞依赖(参考 DEEP_ANALYSIS_REPORT_V3.md 第八节)
5. 添加 pip-audit 到开发依赖,用于定期安全扫描
6. 在 CI/CD 中(如有)添加依赖安全扫描步骤

## 验收标准
- 所有依赖版本精确锁定
- 已知漏洞依赖已升级
- pip-audit 扫描无高危项
```

---

### PROMPT-P3-04: 补充单元测试

```
你是一个测试工程师。请在 PyGBSentry 项目中补充单元测试覆盖率。

## 背景
核心业务逻辑的单元测试覆盖率不足,当前覆盖率约 30-40%。

## 要求
按以下优先级补充测试:

1. backend/app/sip/ 目录(目标 80%):
   - auth.py: Digest 认证各种算法的组合测试
   - handlers.py: 设备注册/注销/心跳/目录上报的测试
   - invite.py: INVITE 流程的各种场景(成功/超时/拒绝)
   - ssrc_manager.py: SSRC 分配/回收的并发测试
   - dialog_manager.py: Dialog 创建/更新/删除的测试

2. backend/app/services/ 目录(目标 70%):
   - stream_session_service.py: 流会话生命周期测试
   - media_manager.py: ZLM 启动/停止/健康检查测试
   - platform_service.py: 级联平台注册/心跳测试

3. backend/app/api/v1/endpoints/ 目录(目标 60%):
   - login.py: 登录/登出/刷新token测试
   - devices/: 设备 CRUD 测试
   - record.py: 录像管理测试

## 约束
- 使用 pytest + pytest-asyncio
- Mock 外部依赖(ZLM、Redis、数据库)
- 测试需可在 CI 中无 Docker 环境运行

## 验收标准
- 整体覆盖率达到 70%
- 核心模块覆盖率达到 80%
- 所有测试通过
```

---

### PROMPT-P3-05: 优化日志级别配置

```
你是一个运维工程师。请在 PyGBSentry 项目中优化日志级别配置。

## 背景
backend/app/main.py 中生产环境日志级别设置为 INFO,可能产生大量日志。

## 要求
1. 在 backend/app/main.py 中根据 APP_ENV 动态设置日志级别:
   - 生产环境(prod): stderr 日志级别为 WARNING
   - 开发环境(dev): stderr 日志级别为 INFO
   - 调试模式(debug): stderr 日志级别为 DEBUG
2. 文件日志(app.log)保持 INFO 级别(等保2.0要求)
3. 审计日志(audit.log)保持 WARNING 级别
4. 添加配置项 LOG_LEVEL_STDERR 覆盖默认值
5. 为关键模块(SIP、流媒体)添加独立的日志级别配置

## 验收标准
- 生产环境 stderr 不输出 INFO 级别日志
- 文件日志级别不受影响
- 可通过配置覆盖日志级别
```

---

### PROMPT-P3-06: 完善健康检查端点

```
你是一个后端工程师。请在 PyGBSentry 项目中完善健康检查端点的详细信息。

## 背景
健康检查仅返回 {"status":"ok"},缺少各子系统的详细状态。

## 要求
1. 阅读 backend/app/api/v1/endpoints/health.py 和 backend/app/main.py 中的 health 端点
2. 增强 /health 端点返回内容:
   {
     "status": "ok|degraded|down",
     "timestamp": "ISO 8601",
     "checks": {
       "database": {"status": "ok", "latency_ms": 5},
       "redis": {"status": "ok", "latency_ms": 2},
       "sip": {"status": "running", "active_dialogs": 15},
       "zlm": [{"id": "zlm1", "status": "online", "latency_ms": 3}],
       "plugins": {"loaded": 5, "active": 4, "error": 1}
     }
   }
3. /health/live 保持轻量(仅返回 alive)
4. /health/ready 返回详细就绪状态
5. 添加 /health/detail 返回完整诊断信息(需管理员权限)
6. 各检查项添加超时保护(单个检查不超过 2 秒)

## 验收标准
- 健康检查返回各子系统状态
- 单个检查失败不影响其他检查
- 响应时间不超过 3 秒
- 详细端点需认证
```

---

### PROMPT-P3-07: 添加 Prometheus 性能指标

```
你是一个监控工程师。请在 PyGBSentry 项目中完善 Prometheus 性能指标。

## 背景
虽然有 /metrics 端点,但指标不够全面,无法有效监控系统的运行状态。

## 要求
1. 阅读 backend/app/core/metrics.py 了解现有指标
2. 添加以下指标:
   - pygbsentry_sip_messages_total{method, direction}: SIP 消息计数
   - pygbsentry_sip_active_dialogs: 活跃 Dialog 数量
   - pygbsentry_sip_invite_duration_seconds: INVITE 延迟直方图
   - pygbsentry_stream_sessions_active: 活跃流会话数
   - pygbsentry_stream_sessions_total{action}: 流会话操作计数
   - pygbsentry_db_pool_size{pool}: 数据库连接池大小
   - pygbsentry_db_pool_in_use{pool}: 数据库连接池使用中数量
   - pygbsentry_plugin_hook_duration_seconds{plugin, hook}: 插件 Hook 执行延迟
   - pygbsentry_memory_usage_bytes: 进程内存使用
3. 在关键代码路径中埋点收集指标
4. 确保 /metrics 端点的 IP 白名单保护仍然有效

## 验收标准
- Prometheus 可抓取到所有新增指标
- 指标命名符合 Prometheus 最佳实践
- 埋点不影响性能(使用 Counter/Histogram 的异步更新)
```

---

### PROMPT-P3-08: 搭建 CI/CD 流水线

```
你是一个 DevOps 工程师。请为 PyGBSentry 项目搭建 GitHub Actions CI/CD 流水线。

## 要求
1. 创建 .github/workflows/ci.yml:
   - 触发条件: push to main, pull request
   - 后端: Python 3.10, 安装依赖, ruff lint, pytest
   - 前端: Node 20, pnpm install, vue-tsc typecheck, vitest, vite build
   - 安全扫描: pip-audit, npm audit
2. 创建 .github/workflows/deploy.yml:
   - 触发条件: push tag v*
   - 构建后端 Docker 镜像并推送到 registry
   - 构建前端 Docker 镜像并推送到 registry
3. 创建 .github/workflows/security.yml:
   - 定时触发(每天)
   - 依赖漏洞扫描
   - 代码静态分析(bandit for Python)
4. 添加缓存策略(pip cache, pnpm store)
5. 添加构建状态徽章到 README.md

## 验收标准
- CI 流水线在 push/PR 时自动运行
- lint、typecheck、test 全部通过
- 安全扫描定期执行
- 构建状态徽章显示在 README
```

---

### PROMPT-P3-09: 提供数据库备份恢复方案

```
你是一个 DevOps 工程师。请为 PyGBSentry 项目提供数据库备份和恢复方案。

## 要求
1. 创建 scripts/backup_db.sh:
   - 支持 PostgreSQL 和 SQLite
   - 支持全量备份和增量备份
   - 备份文件加密(使用 openssl)
   - 自动清理超过保留期的备份
   - 支持配置项: BACKUP_DIR, BACKUP_RETENTION_DAYS, BACKUP_ENCRYPTION_KEY
2. 创建 scripts/restore_db.sh:
   - 从加密备份文件恢复数据库
   - 支持指定恢复时间点(PostgreSQL PITR)
   - 恢复前自动备份当前数据库
3. 更新 docker-compose.yml 添加备份 sidecar 服务:
   - 定时执行备份脚本
   - 备份文件挂载到备份卷
4. 在 config.py 中已有 AUTO_BACKUP_* 配置项,确保脚本与之对齐
5. 编写 docs/backup-restore.md 详细文档

## 验收标准
- 备份脚本可正确备份和恢复数据库
- 备份文件已加密
- 过期备份自动清理
- 文档详细可操作
```

---

## 五、批量修复提示语

### PROMPT-BATCH-01: P0 全部修复

```
你是一个高级全栈安全工程师。请按以下顺序修复 PyGBSentry 项目中的所有 P0 致命问题。

## 修复顺序
1. PROMPT-P0-04: 升级 Docker 镜像版本(最快,无代码改动)
2. PROMPT-P0-02: 加密媒体节点密钥(影响范围小)
3. PROMPT-P0-01: 加密设备密码字段(影响范围大,需迁移)
4. PROMPT-P0-03: 修复 ZLM API 密钥传递(需全局搜索修改)
5. PROMPT-P0-05: 修复全局字典内存泄漏(需仔细测试并发)

## 约束
- 每完成一项修复后运行全部测试,确保不引入回归
- 所有修复需要添加或更新对应的单元测试
- 数据迁移脚本需在 SQLite 和 PostgreSQL 上测试
- 修改需保持向后兼容(旧数据可自动迁移)

## 完成标准
- 所有 P0 问题修复
- 所有测试通过
- 数据迁移脚本可正确迁移现有数据
- 无新增的 lint/typecheck 错误
```

---

### PROMPT-BATCH-02: P1 安全加固

```
你是一个安全工程师。请按以下顺序修复 PyGBSentry 项目中的所有 P1 高危问题。

## 修复顺序
1. PROMPT-P1-03: 实现登录失败次数限制 + 账户锁定(最高优先级)
2. PROMPT-P1-04: 添加密码强度验证
3. PROMPT-P1-01: 前端 localStorage 迁移
4. PROMPT-P1-02: 收紧 CSP 策略
5. PROMPT-P1-06: 配置 SSL/TLS 强制要求
6. PROMPT-P1-07: 优化数据库连接池配置
7. PROMPT-P1-05: 修复异常静默吞没(分批处理)
8. PROMPT-P1-08: 添加登录审计日志

## 约束
- 安全功能需有对应的测试覆盖
- 新增配置项需更新 .env.example
- 用户可见的安全提示需支持 i18n
- 不影响现有功能的正常使用

## 完成标准
- 所有 P1 问题修复
- 安全测试通过(暴力破解、弱密码、XSS 等)
- 现有功能测试通过
```

---

## 六、验证提示语

### PROMPT-VERIFY-01: 修复后全面验证

```
你是一个 QA 工程师。请在 PyGBSentry 项目完成 P0+P1 修复后进行全面验证。

## 验证项目
1. 运行全部后端测试: cd backend && python -m pytest -v
2. 运行全部前端测试: cd frontend && pnpm test
3. 运行 lint: cd backend && ruff check . && cd ../frontend && pnpm lint
4. 运行类型检查: cd frontend && pnpm typecheck
5. 验证数据库迁移: 
   - 创建新的 SQLite 数据库,运行迁移
   - 使用旧数据库备份,运行迁移验证数据完整性
6. 安全验证:
   - 尝试暴力破解登录(应被限流/锁定)
   - 检查 CSP 头是否正确
   - 验证密码强度检查
   - 验证 localStorage 不再存储敏感信息
7. Docker 部署验证:
   - docker compose up -d
   - 验证所有服务健康
   - 验证设备注册和视频播放
8. 性能验证:
   - 并发 100 路 SIP 注册
   - 并发 50 路视频播放
   - 监控内存使用是否稳定

## 输出
生成验证报告,包含:
- 测试通过率
- 发现的回归问题
- 性能基准数据
- 安全验证结果
```

---

## 附录: 提示语使用建议

### 执行策略

| 阶段 | 时间 | 提示语 | 目标 |
|------|------|--------|------|
| 第1周 | Day 1-2 | PROMPT-P0-04, P0-02 | 快速修复低风险 P0 |
| | Day 3-4 | PROMPT-P0-01 | 加密设备密码(需迁移) |
| | Day 5 | PROMPT-P0-03 | 修复 ZLM 密钥传递 |
| 第2周 | Day 6-7 | PROMPT-P0-05 | 修复内存泄漏和竞态 |
| | Day 8-10 | PROMPT-P1-03, P1-04 | 登录安全加固 |
| | Day 11-12 | PROMPT-P1-01, P1-02 | 前端安全加固 |
| | Day 13-14 | PROMPT-VERIFY-01 | 全面验证 |
| 第3-4周 | | PROMPT-P1-05 ~ P1-08 | 其余 P1 修复 |
| 第5-8周 | | PROMPT-P2-* | P2 中危修复 |
| 第9-12周 | | PROMPT-P3-* | P3 优化和基础设施 |

### 注意事项

1. **每次只执行一个提示语**,完成验证后再进行下一项
2. **数据库迁移**相关的修复(P0-01, P0-02, P1-03)需要在维护窗口执行
3. **CSP 策略**修改后需要全面测试前端功能,避免误伤
4. **异常处理**修改(P1-05)建议分批提交,便于 Code Review
5. 所有修复完成后运行 `PROMPT-VERIFY-01` 进行全面验证

---

**文档生成时间**: 2025-01-05  
**基于报告**: DEEP_ANALYSIS_REPORT_V3.md  
**文档作者**: CatPaw (AI代码分析助手)
