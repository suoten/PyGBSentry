# 插件生态与版本能力对照（细项）

> 本文档对照「产品设想」与当前仓库实现，标注：**✅ 已完成**、**⚠️ 部分完成**、**❌ 未完成/缺失**。  
> 范围：`editions/open-source`（开源版 OSS）与 `editions/server`（服务器版）。  
> 更新说明：实现以代码为准；若后续迭代，请同步修订本表。

**官方插件角标**、**官方微信/支付宝支付** 的术语、规则、接口约定与「先文档后代码」排期见下方 **§0.1～§0.5**（与本对照表同文，不再拆到其它文件）。

---

## 0. 快速索引（实现落点）

| 主题 | 主要代码位置 |
|------|----------------|
| OSS 插件加载与 Hook | `open-source/backend/app/core/plugin_manager.py` |
| OSS 插件 HTTP API（市场、安装、卸载、运行时） | `open-source/backend/app/api/v1/endpoints/plugins.py` |
| 服务器版插件与市场 | `server/backend/app/api/v1/endpoints/plugins.py` |
| 许可证签名/校验（Ed25519） | 两侧 `app/services/license_service.py` |
| 计费、订单、分成、提现 | `server/backend/app/api/v1/endpoints/billing.py`、`app/models/billing.py` |
| OSS 配置项（市场 URL、上报 URL） | `open-source/backend/app/core/config.py`（`PLUGIN_*`） |
| 插件规范（开发者向） | `open-source/docs/PLUGIN_SPEC.md` |
| 前端插件中心 | `open-source/frontend/src/views/PluginCenter.vue` |
| 官方插件 `is_official`（catalog + 审核/管理 API） | `server/.../plugins.py`；`plugins/marketplace.json` |
| 官方支付（微信/支付宝） | `server/.../billing.py`、`app/services/payment_service.py` |

**P2 双端购买授权**（回归清单、执行顺序、日报/周报模板、对外同步口径）：详见本文 **§6.1**，并与服务器版盘点 **§6.3**（`editions/server/服务器版_产品与插件系统实施盘点.md`）对齐；改判条件见 **§6.1.3**。

---

### 0.1 术语

| 术语 | 含义 |
|------|------|
| **官方插件** | 由平台运营方审核上架、在插件市场中标记为「官方」的插件；与第三方开发者上架插件在展示与信任层级上区分。 |
| **官方支付** | 插件订单在服务器版中通过 **微信支付（V3 Native）** 与 **支付宝（电脑网站）** 完成收款；二者为各支付机构官方开放能力，需商户号/应用与回调配置，运维细则见 `editions/server/docs/PAYMENT_SETUP.md`。 |
| **模拟支付** | 开发/联调用 `mock` 通道，不产生真实资金；不作为「官方支付」对外宣传。 |

### 0.2 官方插件标识（「官方标志」）

#### 产品目标

- 用户在 **服务器版插件商城**、**开源版插件中心**（拉取同一 catalog 时）能一眼识别 **官方认证/官方上架** 插件。
- 与 **第三方作者** 插件在 UI 上区分（例如角标、标签文案「官方」）；与「强烈推荐」等运营标签并存时，文案上统一用 **「官方」** 表示发布者身份。

#### 建议规则（供实现时采用）

1. **数据来源**：以 `marketplace.json`（及审核通过写入库表/条目的元数据）为权威。增加布尔或枚举字段（二选一，实现时统一即可）：`is_official: true | false`，或 `publisher: "platform" | "third_party"`（`platform` 视为官方）。
2. **谁可标为官方**：**仅平台管理员**在审核通过或编辑 catalog 时可设为官方；第三方作者默认 `false` / `third_party`；平台自营插件应标为官方。
3. **展示位置（改代码时覆盖）**：服务器版 `Marketplace.vue` 等列表/详情；开源版 `PluginCenter.vue`、插件详情页（若有）——插件名称旁 **官方** 角标（与「推荐」「已废弃」等并列时注意层级）。
4. **与现有字段关系**：`is_featured`（推荐）与 `is_official`（官方）**正交**，可并存；实现阶段需补：**API 返回字段** + **前端组件** + **后台编辑入口**（若尚无）。

**实现说明（已与代码对齐）**：`plugins/marketplace.json` 支持布尔字段 **`is_official`**（示例：`mobile_app_suite` / `mini_program_suite` / `tv_wall_suite` 为 `true`，其余条目默认 `false`）。服务器版 **`PUT /api/v1/plugins/marketplace/submissions/{id}/approve`** 可在通过时写入 `is_official`；**`PUT /api/v1/plugins/marketplace/{plugin_id}`**（管理员）可修改。公共列表 **`GET .../marketplace/public`** 原样透传该字段。前端角标：**服务器版** `Marketplace.vue`、`PluginDetail.vue`、`BillingCenter.vue`、`PluginDeveloper.vue`（含审核确认与目录编辑）；**开源版** `PluginCenter.vue`、`PluginDetail.vue`。

### 0.3 官方支付（微信 + 支付宝）

| 细项 | 说明 |
|------|------|
| **范围** | 仅 **服务器版**计费：`/api/v1/billing/*` 插件订单。 |
| **含义** | 用户选择 **微信支付** 或 **支付宝** 完成支付；依赖后台 `PaymentConfig` 与公网回调地址。 |
| **运维与密钥** | 环境变量、商户平台配置、回调 URL：**`editions/server/docs/PAYMENT_SETUP.md`**。 |
| **接口约定**（以代码为准，此处对齐预期） | 创建订单 `POST /api/v1/billing/orders`（`pay_channel`: `wechat` \| `alipay` \| `mock`）；异步通知 `POST /api/v1/billing/payment/notify/wechat`、`.../alipay`；渠道是否可用 `GET /api/v1/billing/payment/channels`（用于前端默认支付方式）。 |
| **与「官方插件」关系** | **官方支付** = 钱怎么收；**官方插件** = 谁发布的插件；二者独立，文案可并列：「官方插件商城支持官方微信/支付宝支付」。 |

### 0.4 文档先行：后续改代码建议顺序

下列顺序供 **文档评审通过后** 排期使用（与「本对照表定稿」同步）。**第 2～3 步已在仓库落地**；第 4 步依赖商户号与公网回调，由运维在自有环境完成。

| 顺序 | 内容 | 说明 |
|------|------|------|
| 1 | 冻结本对照表相关章节 + `PAYMENT_SETUP.md` | 产品与运维对回调地址、官方定义、角标规则达成一致。 |
| 2 | 官方支付（与文档对齐） | ✅ 已落地：`billing` / `payment_service`、异步通知、`GET /api/v1/billing/payment/channels`、计费页「官方微信/支付宝」选项与默认渠道；详见 **§0.3** 与 `PAYMENT_SETUP.md`。 |
| 3 | 官方插件标识 | ✅ 已落地：详见 **§0.2** 实现说明（catalog、`is_official`、审核与管理员编辑、双端角标）。 |
| 4 | 联调与验收 | 在配置商户与 `PAYMENT_NOTIFY_BASE_URL` 后：真实小额单走微信/支付宝；各端列表官方角标抽检。 |

### 0.5 官方相关能力摘要（对照状态）

| 细项 | 状态 | 说明 |
|------|------|------|
| **官方插件** UI 角标（商城/插件中心区分平台上架与第三方） | ✅ | **`is_official`** + 前端展示；规则与入口见 **§0.2**。 |
| **官方支付**（微信 V3 Native + 支付宝电脑网站） | ✅ | 代码与下单流程已集成；**生产收款**依赖商户配置与 **§0.4 第 4 步** 联调（非代码缺口）。 |

---

## 1. 产品版本定位

### 1.1 开源版（OSS）

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 可私有部署 | ✅ | 独立 `editions/open-source`，Docker/README 等部署路径存在。 |
| 核心 GB28181/业务不依赖官方云 | ✅ | 与插件商城解耦，靠配置连接服务器版。 |
| 不含「官方运营」的支付/审核/上架 | ⚠️ | **无**面向公众的「提交到官方商城」流程；但 OSS 提供 **仅超管** **`POST /api/v1/plugins/upload`** 本地上传安装，属**自建/内测**，**不是**开放给终端用户的「官方应用商店」路径——与「开源版不承担平台运营」**不矛盾**（详见 **§5 P2**）。 |

### 1.2 服务器版（Server）

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 官方插件商城与账户体系 | ✅ | 服务器版前端 + `APP_EDITION`、用户/租户模型。 |
| 插件上传、审核、销售、分成、提现 | 部分 | 上传与审核、订单、结算、提现 **已实现**；**下单 / 提现申请**进程内限流见 **§2.3**；订单响应与列表附带 **`purchase_policy`**（默认不可退说明）；**提现侧**已具备多层级风控、审计、**DB 阈值覆盖**与运营接口（见 **§2.3**、**§6**）；其中 **支付通道级异常图谱**（按 `pay_channel` 的处置统计）已落地，**跨租户风险资产追踪 MVP**（支持 IP/设备指纹哈希命中聚合 + `user_id` 命中聚合 + `plugin_id`（订单场景）命中聚合 + 全局黑名单管理）已可用，并提供可开关的自动封禁（基于 rate-limit 命中聚合阈值）；仍缺更完整的多维联动与更多追踪维度扩展。 |

---

## 2. 服务器版：插件生态流程

### 2.1 开发者上传插件

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 交付物为 `.zip`，内含 `plugin.json` | ✅ | `POST /api/v1/plugins/marketplace/submissions`，解压校验 `plugin.json`。 |
| 防重复提交（同作者、同插件、同版本 pending/approved） | ✅ | 数据库查询 `PluginMarketplaceSubmission`。 |
| 管理端自动通过（超管 + `auto_approve`） | ✅ | 可直接写入 `plugins/marketplace.json`。 |
| 插件开发规范（菜单、tables、Hook、`register`） | ✅ | `_validate_plugin_json`、`POST /validate-upload` 等；与 OSS `PLUGIN_SPEC.md` 一致方向。 |
| **插件包整体加密**或**官方包签名（防篡改包体）** | 部分 | 当前为明文 ZIP（未做包整体加密）；但当 catalog 提供 `package_signature`（Ed25519）且配置 `PLUGIN_PACKAGE_ED25519_PUBLIC_KEY` 时，`marketplace/install` 支持对下载后的 ZIP 做整包签名验签；是否强制以 `PLUGIN_PACKAGE_SIGNATURE_REQUIRED` 等配置为准。 |
| 包托管地址 `package_url` | ✅ | 提交时填写 URL；上架写入 catalog。 |

### 2.2 官方审核

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 审核队列与状态 | ✅ | `PluginMarketplaceSubmission`：`pending` / `approved` / `rejected` 等。 |
| 管理端通过/驳回 | ✅ | `PUT /marketplace/submissions/{id}/approve`、`.../reject`，驳回含 `reject_reason`；通过时可写 **`is_official`**。 |
| 上架可见性 | ✅ | `publish_status`（如 `active` / `unlisted`）；公共列表 `_filter_public_marketplace_items` 过滤 `unlisted`。 |
| **官方插件标记** `is_official` | ✅ | 写入 **`marketplace.json`**；管理员 **`PUT /marketplace/{plugin_id}`** 可改；公共接口透传。 |
| **自动化安全审计**（恶意代码扫描、依赖审计） | 部分 | 已加入轻量级静态“危险用法”探测：扫描插件包内 `.py` 文件中的 **进程/命令执行**（`dangerous_call:*` 如 `subprocess` / `os.system` / `eval` 等）、**本地资源/原生扩展**（`native_api:*` 如 `ctypes` / `multiprocessing`）、**反序列化攻击面**（`deserialization:*` 如 `pickle.loads` / `pickle.load`），以及常见 **网络访问/远程管理库**（`network_lib:*` 如 `requests` / `httpx` / `urllib` / `socket` / `paramiko`）；同时从 `requirements*.txt` / `constraints*.txt` 做依赖来源与级联引用探测，并补充扫描 `pyproject.toml` / `setup.cfg` / `setup.py` 中出现的依赖来源关键字段（`dependency_*` 规则：`git+` 源、自定义 index、`-r`/`-c` 级联等）。支持对 `-r` / `-c` 引用的 requirements/constraints 在 ZIP 内做递归展开后继续探测；在 `POST /api/v1/plugins/validate-upload` 与安装阶段以 `warnings`/`errors` 形式返回，可通过 `PLUGIN_SECURITY_SCAN_ENABLED`、`PLUGIN_SECURITY_SCAN_MAX_*` 与 `PLUGIN_SECURITY_SCAN_BLOCK_ON_HIT` 控制是否启用、采样阈值与是否阻断安装。**仍未实现完整依赖解析审计与插件沙箱执行**（不会动态跑代码）。在命中时会返回结构化 `security_report`，便于前端展示与落库。具体规则与建议见 `PLUGIN_SPEC.md`「安全与依赖约束」一节。 |
| **动态沙箱执行** 插件 | 部分 | 已加入“Hook 执行超时隔离”：当开启 `PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS>0` 时，Hook 回调超时将被跳过；同时会触发 `HOOK_ON_ALARM` 走现有告警插件链路。可通过 `POST /api/v1/plugins/hook-timeout-test` 验证超时是否触发告警（本地记录见 `logs/plugin_hook_timeout_test/`）。在可 pickle 的前提下，可选 `PLUGIN_HOOK_EXEC_TIMEOUT_MODE=process` 对“同步回调”进行进程级 terminate；并在支持的 POSIX 环境下为子进程设置 `RLIMIT_CPU`（用超时秒数推导）以及可选的 `RLIMIT_AS`（受 `PLUGIN_HOOK_EXEC_RLIMIT_AS_MB` 控制）以抑制 CPU 密集/内存膨胀型死循环；但仍不等同于完整进程级动态沙箱。 |

### 2.3 销售与分成

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 创建订单、对接支付网关 | ✅ | `billing.py` 内微信/支付宝等下单与回调（需后台配置支付参数）。 |
| 支付成功 → 订单 `paid` | ✅ | `PluginOrder` 与回调验签逻辑。 |
| 支付成功 → 分成结算 `PluginSettlement` | ✅ | `_create_settlement_for_order`，`platform_revenue_ratio` 来自 `PaymentConfig`。 |
| 作者可查询收入与提现 | ✅ | 如 `/billing/withdrawals/me`、`POST /billing/withdrawals`；管理员审核 `PUT .../withdrawals/{id}/status`。 |
| **「插件购买后不支持退款」产品与 API 对齐** | ✅ | **`POST /api/v1/billing/orders`** 与 **`GET /api/v1/billing/orders/me`** 返回体含 **`purchase_policy`**：`refund_eligible`（默认 **`BILLING_PLUGIN_ORDER_REFUND_ELIGIBLE=false`**）、`terms_notice`（可用 **`BILLING_PLUGIN_ORDER_TERMS_NOTICE`** 覆盖默认文案）。**不替代**支付渠道的退款能力，也不强制改订单状态机；运营条款仍需自行完备。 |
| **异常订单风控**（同 IP/同设备指纹多次购买等） | 部分 | **`POST /api/v1/billing/orders`** 增加**进程内**限流：默认同一用户 **≥5s** 间隔（`BILLING_PLUGIN_ORDER_MIN_INTERVAL_SECONDS`）、**每用户每窗口**最多 **30 单**（`BILLING_PLUGIN_ORDER_RATE_WINDOW_SECONDS` 默认 3600s，`BILLING_PLUGIN_ORDER_MAX_PER_USER_PER_WINDOW`）；限流维度进一步按 `pay_channel` 分桶（同理支持 **按 IP**、**按设备指纹** 上限可选：`BILLING_PLUGIN_ORDER_MAX_PER_IP_PER_WINDOW` / `BILLING_PLUGIN_ORDER_MAX_PER_DEVICE_PER_WINDOW`，默认均 **0** 关闭；需请求头携带 `x-device-id` / `x-device-fingerprint` 等）。多实例需网关/业务层补强。 |
| **提现申请频率** | 部分 | **`POST /api/v1/billing/withdrawals`**：**进程内**限流——默认同一用户 **≥30s** 间隔（`BILLING_WITHDRAWAL_MIN_INTERVAL_SECONDS`）、**每用户每窗口**最多 **10** 次（`BILLING_WITHDRAWAL_RATE_WINDOW_SECONDS` 默认 **86400s**，`BILLING_WITHDRAWAL_MAX_PER_USER_PER_WINDOW`）；**按 IP** 可选（`BILLING_WITHDRAWAL_MAX_PER_IP_PER_WINDOW`，默认 **0**）；**按设备指纹**可选（`BILLING_WITHDRAWAL_MAX_PER_DEVICE_PER_WINDOW`，默认 **0**；需请求头携带 `x-device-id` / `x-device-fingerprint` 等）。此外可选配置 `BILLING_WITHDRAWAL_MIN_SETTLEMENT_AGE_SECONDS`：提现仅允许从“已成熟结算”中提取；可选配置 `BILLING_WITHDRAWAL_CREATE_REQUIRE_SENSITIVE_CONFIRM`：创建提现也要求 OTP/密码二次确认。 |
| **提现风控与阈值运营（Server）** | ✅ | 在 **§5 P0「服务器版订单风控」** 与 **§6** 附录中汇总：除进程内限流外，含 **账号/支付链路** 风控、**review** 队列、`risk_disposition`、**审计**、**webhook**、多维度 **disposition 统计**、**只读建议/预演**，以及 **`system_settings.billing_withdrawal_risk_overrides`**（与 env 合并、**diff_vs_env**、**apply** / **clear**）。管理端 **`editions/server/frontend/.../AdminWithdrawals.vue`** 提供 **仅风控复核** 列表、`risk_disposition` 可选录入；**风控命中审计**（可选 **`action`/`result`** 与时间及分页）、**处置统计（总体/按规则/按租户/租户×规则，含 min_total 与分页）**（均支持可选 **`start_at`/`end_at`**）；**阈值建议 / DB 覆盖 / 试算日志**（可选 **`audit_result`** 与 **`start_at`/`end_at`**）、**预演**、**试算（dry_run）/应用**（独立时间筛选）与 **按 scope 清除 DB 覆盖（POST .../clear）** 入口，并支持 **一键刷新风控运营面板**（静默并行刷新全部上述数据块）。页面会用 **localStorage** 记住上述筛选条件与分页参数，刷新后自动恢复；同时支持 **一键重置筛选与分页**（清空本地状态并回到默认值），以及将当前结果导出为 **CSV**（命中审计 / 按租户 / 租户×规则 / 试算日志），并可按当前筛选分页拉取导出 **全量匹配** 的命中审计与试算日志。运营使用指引见 `editions/server/docs/BILLING_WITHDRAWAL_RISK_RUNBOOK.md`。 |
| **`install-check` / 安装 `record-event` 校验单品权益** | ✅ | Server **`PLUGIN_INSTALL_CHECK_REQUIRE_ENTITLEMENT`**（默认 **true**）：对 catalog 中 **`type=paid`**，在订阅有效前提下还要求 **`plugin_id` ∈** 与 **`GET /purchased`** 相同的集合（**`PluginOrder(status=paid)` ∪ 当前有效套餐 `plugin_entitlements`**）；否则 **403**（主路径为结构化 `detail.reason_code=PLUGIN_NOT_PURCHASED`，兼容旧字符串 detail）。**false** 时恢复仅拦截订阅过期的旧行为。 |
| **租户在服务器版一键 `POST .../marketplace/install`** | ✅ | 与上述 **`install-check` / `record-event`** 共用 **`_require_paid_plugin_install_entitlement`**；请求体带 **`package_url` 覆盖地址**时，**`type=paid`** 仍以**本地 `marketplace.json` 条目**为准，避免绕过付费校验。 |

---

## 3. 开源版：插件中心与服务器版联动

### 3.1 配置与鉴权契约

| 配置项（OSS `config`） | 用途 | 说明 |
|------------------------|------|------|
| `PLUGIN_MARKETPLACE_BASE_URL` | 服务器版站点根 URL | 用于拉取 `GET {base}/api/v1/plugins/marketplace/public`。 |
| `PLUGIN_SERVER_RECORD_URL` | 安装/卸载上报 | `POST` 到服务器版 `record-event` 类地址；也用于推导「服务器 base」做 `install-check`、代理 `purchased`。 |
| `PLUGIN_PAID_RUNTIME_INSTALL_CHECK` | 付费插件 **runtime** 与 **install-check** | 默认 **false**：付费插件访问 **`/plugins/runtime/*`**、**`/plugins/plugin-assets/*`** 时仅用 **`/purchased` 代理**（受 **`PLUGIN_PURCHASED_PROXY_CACHE_SECONDS`** 影响）。**true** 且已配置服务器 base 时：**每次请求**向服务器版 **`POST .../install-check`**（与安装预检同源），成功后**清除该用户已购代理缓存**；网络/严格策略同 **`PLUGIN_PAID_INSTALL_CHECK_STRICT`**。 |
| `PLUGIN_PAID_INSTALL_CHECK_STRICT` | 付费插件 `install-check` | 默认 **true**：已配置服务器 base 且 **`type=paid`** 时预检须 **HTTP 2xx + `{"ok": true}`**，超时/连接失败/其它非 2xx（除已单独处理的 **401/402/403**）在 strict 下**阻断安装**。**401/402/403** 无论 strict 均**阻断**。**false** 时仍拦 **401/402/403**，其余异常不拦（旧版「网络故障不挡安装」）。 |
| `PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS` | 付费插件 **Hook** 与 license | **OSS + Server** `plugin_manager.emit`：对 **`type=paid`**、且**非** `on_startup` / `on_shutdown` / `on_uninstall` 的回调，按间隔**重读**磁盘 **`license.json`** 并校验签名/期限；失败则**跳过本次 Hook**（默认 **60s**，**0**=每次触发都校验）。此外在进程内启动后台循环按同一间隔对已加载 paid 插件 **强制重验 license**，确保订阅过期后在最多一个间隔内停用相关 Hook（**`0`** 时后台同步关闭）。**不**替代 HTTP **`/purchased`**。 |
| `PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS` | 插件 Hook 执行超时隔离 | **OSS + Server** `plugin_manager.emit`：当值 **>0** 时，对 Hook 回调做超时保护；协程用 `wait_for`，同步回调按 `PLUGIN_HOOK_EXEC_TIMEOUT_MODE` 执行超时隔离（默认 thread 超时跳过；可选 process 对同步回调在超时后 terminate 子进程）。 |
| `PLUGIN_HOOK_EXEC_TIMEOUT_MODE` | 插件 Hook 超时隔离模式 | `thread`（默认）：同进程线程池 wait_for；`process`：对“可回放的同步模块级函数”在超时后 terminate 子进程（参数需可 pickle）。 |
| `PLUGIN_HOOK_EXEC_RLIMIT_AS_MB` | Hook 进程模式内存上限 | 仅在 `PLUGIN_HOOK_EXEC_TIMEOUT_MODE=process` 且 POSIX 环境下生效，通过 `RLIMIT_AS` 对子进程设置内存上限（MB）；<=0 表示不限制。 |
| `PLUGIN_SECURITY_SCAN_ENABLED` | 插件安全扫描开关 | Server：`validate-upload` 与安装阶段对插件包做轻量级静态扫描（代码关键API探测 + `requirements*.txt` / `constraints*.txt` 依赖来源/级联引用探测）。 |
| `PLUGIN_SECURITY_SCAN_BLOCK_ON_HIT` | 扫描命中策略 | Server：命中危险片段时是否阻断（`true` 阻断安装/校验返回 errors；默认仅告警）。 |
| `PLUGIN_SECURITY_SCAN_MAX_FILE_COUNT` | 扫描文件上限 | Server：扫描 `.py`/`requirements*.txt`/`constraints*.txt` 以及 `pyproject.toml` / `setup.cfg` / `setup.py` 的最大文件数量（避免过度耗时）。 |
| `PLUGIN_SECURITY_SCAN_MAX_FILE_BYTES` | 单文件读取上限 | Server：对每个扫描文件最多读取的字节数上限。 |
| `PLUGIN_SECURITY_SCAN_MAX_HITS` | 命中上限 | Server：最多收集的命中数上限（超过即提前返回）。 |
| `PLUGIN_MARKETPLACE_SHOP_URL` | 「购买」按钮 | 可选；不填则回退 `PLUGIN_MARKETPLACE_BASE_URL`。 |
| `PLUGIN_MANIFEST_ED25519_PUBLIC_KEY` | **plugin.json 清单签名** | 可选 PEM；未设置时回退 **`LICENSE_ED25519_PUBLIC_KEY`**。包内 **`manifest_signature`** 存在时**必须**能验签，否则安装失败。 |
| `PLUGIN_MANIFEST_SIGNATURE_REQUIRED` | 强制清单签名 | 默认 **false**；**true** 时 **`plugin.json` 必须**含有效 **`manifest_signature`**（见 **§3.3**）。 |
| `PLUGIN_PACKAGE_ED25519_PUBLIC_KEY` | 插件包（ZIP 整包）签名验签公钥 | 可选；未设置时回退 **`LICENSE_ED25519_PUBLIC_KEY`**。catalog 提供 `package_signature` 时用于验签。 |
| `PLUGIN_PACKAGE_SIGNATURE_REQUIRED` | 强制包签名 | 默认 **false**；仅当 `marketplace/install` 从 catalog 期望到 `package_sha256`（expected_package_sha256 非空）且本项为 `true` 时，才要求必须提供 `package_signature`。 |

**鉴权方式**：浏览器/客户端在请求 OSS API 时携带 `Authorization`（与登录服务器版同一 token 体系时），OSS 后端**原样转发**到服务器版 `GET /api/v1/plugins/purchased` 等。

### 3.2 插件市场列表（内容来源）

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| OSS `GET /api/v1/plugins/marketplace` | ✅ | 若 `APP_EDITION==server` 读本地 catalog；否则 **`_fetch_marketplace_items()`** 实时请求服务器 `marketplace/public`。 |
| 请求失败回落本地 `plugins/marketplace.json` | ✅ | 便于离线或调试。 |
| 字段兼容（`name`/`title`、`menu.title`） | ✅ | `_fetch_marketplace_items` 内做了补齐。 |
| **独立字段：「允许被 OSS 拉取」**（除 `status`/`min_oss_version` 外） | ⚠️ | 无单独 `allow_oss` 字段；通过 **`status`（如 deprecated）**、**`min_oss_version` vs `PROJECT_VERSION`** 等组合控制。 |

### 3.3 购买与安装

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 前端「购买」跳转商城 | ✅ | `GET /api/v1/plugins/marketplace-shop-url`。 |
| 已购列表（隐藏「购买」、仅「安装」） | ✅ | `GET /api/v1/plugins/purchased`（OSS 代理服务器版）。 |
| 从市场安装 `POST /api/v1/plugins/marketplace/install` | ✅ | 解析 `package_url`（须 **允许域名** `_is_allowed_package_url`，与 `PLUGIN_MARKETPLACE_BASE_URL` 主机一致或 localhost）。 |
| 下载 ZIP | ✅ | `requests.get`；HTTP 状态码校验。 |
| 解压 | ✅ | `safe_extract_zip`（防路径穿越）。 |
| 付费插件：`license.json` / `metadata.license` + `verify_plugin_license` | ✅ | 与租户 `tenant_id` 绑定校验。**目录包**：**OSS 与 Server** 均在 **`load_plugins`** 时 **`type=paid` 且 license 有效** 才加载（已去除错误的 **`APP_EDITION==server`** 前置条件，与「开源侧安装 + 签发 license」一致）。 |
| 付费插件：安装前 `POST .../install-check` | ✅ | **市场安装**与 **超管本地上传**（解压前读取 `plugin.json`）均会预检；订阅过期 **402**、未购或套餐不含该插件 **403**。当前主路径已统一为**结构化 `detail.reason_code`**：`SUBSCRIPTION_EXPIRED` / `PLUGIN_NOT_PURCHASED`（仍兼容旧字符串 detail，Server **`PLUGIN_INSTALL_CHECK_REQUIRE_ENTITLEMENT`**，**§2.3**）；**`PLUGIN_PAID_INSTALL_CHECK_STRICT`** 见 **§3.1**。 |
| 安装/升级后 `record-event` | ✅ | **`_notify_server_plugin_event`**：**402** / **403** 均**向上抛出**；并与 install-check 一样优先返回结构化 `detail.reason_code`（`SUBSCRIPTION_EXPIRED` / `PLUGIN_NOT_PURCHASED`）。**403** 与 **402** 一样触发 **`_rollback_installed_plugin_files`**（市场安装与本地上传），避免「本地已解压但服务器不认权益」。 |
| **下载完成后与官方清单比对 SHA256/签名** | 部分 | **可选 SHA256**：catalog **`package_sha256`/`sha256`** 时 OSS/Server **`marketplace/install`** 校验 zip（见 **§5 P0**）。**plugin.json Ed25519 manifest 签名**（**`manifest_signature`** / **`manifest_sig_alg`**）可选；配置公钥或 **`PLUGIN_MANIFEST_SIGNATURE_REQUIRED`** 时安装与 **`validate-upload`** 校验（见 **§3.1**、**`license_service.sign_plugin_manifest_payload`**）。此外可选：catalog 提供 `package_signature` 且配置 `PLUGIN_PACKAGE_ED25519_PUBLIC_KEY` 时，对 ZIP 做整包签名验签（默认不强制，见 **`PLUGIN_PACKAGE_SIGNATURE_REQUIRED`**）。 |
| **插件数据表命名强制 `plugin_xxx_` 前缀** | 部分 | 默认**关闭**；**OSS 与 Server** 均支持 **`PLUGIN_TABLES_REQUIRE_PLUGIN_ID_PREFIX=true`**：**安装**阶段校验 **`plugin.json.tables`** **`plugin_{id}_` 前缀**（见 `PLUGIN_SPEC.md`）。**卸载**仍为字符白名单。 |
| 建表 | 部分 | `tables` 声明后触发 `Base.metadata.create_all`；具体 ORM 模型需插件包内注册。 |

> 自动建表的“可验收口径”（为何当前仍是 `部分`）：
>
> - 当前可保证的建表路径是“插件在加载后确实注册了 ORM 模型”→ `create_all` 才能创建出表。
> - `plugin.json.tables` 当前更多承担“卸载预览/卸载删除目标列表”的声明职责，**不等价于完整 DDL**；仅声明 `tables` 但未提供/注册 ORM 模型时，不保证一定能创建出表。
> - 升级时的“字段变更/数据迁移”不应由 `create_all` 隐式承担，统一走 `HOOK_ON_UPGRADE`（见下行）作为显式迁移入口。
>
> 建议的回归样例（用于将本项从 `部分` 改判为 `✅`）：
>
> - 样例 A（最小 ORM 建表）：1 张简单表（主键+字段）安装后存在；重复安装/加载幂等。
> - 样例 B（关系/约束）：2 张表（含外键或唯一约束）安装后约束存在；卸载后清理一致。
> - 样例 C（升级/迁移）：升级新增字段/新增表时，通过 `HOOK_ON_UPGRADE` 执行必要 DDL/DML，并能留证据（日志/SQL/页面）。

### 3.4 菜单与授权展示（PC）

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| OSS 下列出插件菜单 `GET /api/v1/plugins/menus` | ✅ | **付费插件**：仅当 **`/purchased` 代理**含该 `plugin_id` 才透出；**超管**与 **`/runtime`、mobile-entries** 一致不过滤。 |
| Server 版下列菜单 `GET /api/v1/plugins/menus` | ✅ | **付费插件**：非超管与 **`GET /purchased`** 同源（**`_tenant_purchased_plugin_ids`**）；**超管**不过滤。返回项与 OSS 对齐增加 **`frontend_url`**（便于 PC 侧栏 iframe/WebView）。 |

### 3.5 移动端入口（与菜单一致性）

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| `GET /api/v1/plugins/mobile-entries` | ✅ | **OSS**：**付费插件**仅当 **`/purchased` 代理**含该 `plugin_id` 才透出；**超管**与 **`/runtime` 验权**一致不过滤。**Server**：与 **`GET /purchased`** 同源 **`_tenant_purchased_plugin_ids`**；**超管**不过滤。 |
| **`GET/PUT .../runtime/{plugin_id}/config`（Server）** | ✅ | **付费插件**：非超管须租户权益含 `plugin_id`（与 **`/purchased`** 同源），否则 **403**。 |

### 3.6 运行时授权校验（你设想中的重点）

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 安装时：服务器 `install-check` + 本地 license | ✅ | 见 3.3。 |
| **OSS：插件运行时 HTTP API**（`/plugins/runtime/*` + `/plugins/plugin-assets/*`）对 **metadata.type=paid** 的已加载插件 | ✅ | 依赖 **`require_oss_paid_runtime_from_path`**：与 **`/menus`** 一致，用 **`/purchased`** 代理结果校验；**超管豁免**。**不**等于「每个非 `plugins` 业务路由都验权」。 |
| **Server：`GET .../plugin-assets/...`** | ✅ | 与 OSS 同路径；**paid** 走 **`_require_server_paid_runtime_entitlement`**（DB **`/purchased`** 同源）；静态查找顺序与 OSS 一致（**`plugins/{id}`**、**`dist`/`www`/`frontend`**）。**iframe**：**`deps.get_current_user`** 支持 **`?token=`**（与 OSS 一致），供 **`PluginRuntime.vue`** 内嵌静态页鉴权。 |
| **业务 Hook（SIP/告警/ZLM 等）与 `type=paid`** | ✅ | **`emit`** 在 **`on_startup`/`on_shutdown`/`on_uninstall`** 外对付费插件按 **`PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS`** **复检本地 license**；同时由进程内后台循环定时“强制重验”，确保订阅过期后在最多一个间隔内停用回调。**仍不**向服务器拉 **`/purchased`**（与 HTTP 入口策略不同）。 |
| **每次 runtime 请求服务器 install-check**（与 `/purchased` 缓存对比） | ✅ | **安装路径**：付费插件在 strict 下 **`install-check` 须成功**后才解压（见 **§3.3**）。**运行时**：默认 **`/purchased`** 代理 + **`PLUGIN_PURCHASED_PROXY_CACHE_SECONDS`**（默认 **45s**，**0** 关闭）；安装/上传成功后会 **`invalidate_...`**。可选 **`PLUGIN_PAID_RUNTIME_INSTALL_CHECK=true`**：在 OSS 已配置服务器 base 且目标插件 `metadata.type=paid` 时，对 **`/plugins/runtime/*`**、**`/plugins/plugin-assets/*`** **每次请求**额外进行 **服务器端 `install-check`**，成功后刷新已购代理缓存（见 **§3.1**）。**服务器版** runtime 权益为 DB 直读，无 OSS 侧代理缓存问题。 |
| **定时任务同步授权**（防盗用、订阅过期后自动禁用） | ✅ | 已实现：OSS/Server 在进程内启动后台循环，按 **`PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS`** 对已加载 paid 插件 **强制重验本地 `license.json`** 并更新授权状态；Hook 侧使用缓存跳过无效回调，实现订阅过期后自动禁用（最大延迟约一个间隔）。 |

### 3.7 插件更新

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| 再次从市场安装同 id | ✅ | `_install_plugin_from_zip` 中 `operation` 可为 `upgrade`。**前端**：响应含 `operation` 时，**首次安装**成功仍跳转运行页（OSS/Server 插件详情与 OSS 插件中心）；**升级**成功仅 Toast 提示版本并留在当前页（避免打断阅读详情/市场列表）。 |
| **专用「检查更新」接口**（对比已装 `version` 与 catalog `version`） | ✅ | **`GET /api/v1/plugins/marketplace/update-summary`**；**OSS** `PluginCenter.vue` 展示 **可更新** 角标；**Server** 用户侧 **`PluginCenter.vue`**（列表 **「更新」**）与 **`PluginDetail.vue`**（角标 + **「更新」**）均拉取该接口，已安装且 `has_update` 时走 **`POST .../marketplace/install`**。Server `PluginCenter.vue` 现已补 **`useActivatedRefreshOnce`**，二次激活会自动并行重拉版本与列表数据。 |
| **详情页路由参数切换**（同组件实例复用） | ✅ | **`/console/plugins/detail/:pluginId`**（Server）、**`/plugins/detail/:pluginId`**（OSS）在仅变更 `pluginId` 时可能不再次 `onMounted`：**Server** `PluginDetail.vue` 对 `pluginId` 做 **`watch`** 并重拉市场/已装/更新摘要、评分与插件文档；并补充二次 **`onActivated`** 刷新（首激活不重复请求），对未来 keep-alive 包裹保持兼容；相关二次激活刷新逻辑已统一为 **`useActivatedRefreshOnce`** 组合式实现。**OSS** `PluginDetail.vue` 同样 **`watch`** 并重拉列表数据；因 **`App.vue`** 对 `keepAlive` 路由使用 **`<keep-alive>`**，另在二次 **`onActivated`**（如从运行页返回）时 **`loadData`**，避免安装/可更新角标陈旧。**公开商城** **`/market/:pluginId`** 的 **`PublicPluginDetail.vue`** 亦 **`watch(pluginId)`** 重拉公开详情与公开文档，并在切换插件时置 **`loaded=false`**；同时补充二次 **`onActivated`** 刷新（首激活不重复请求）。 |
| **运行页 / 运行配置路由参数切换** | ✅ | **`/console/plugins/runtime/:pluginId`** 与 **`.../runtime/:pluginId/config`**（Server）、**`/plugins/runtime/:pluginId`**（OSS）：同组件复用时需重绑 iframe 或 schema。**Server** **`PluginRuntime.vue`**：**`watch(pluginId)`** + **`loadRuntimeEntry`**（请求过程中校验当前 `pluginId`，避免过期响应写错 iframe），并补充二次 **`onActivated`** 刷新（首激活不重复请求）以兼容未来 keep-alive 包裹。**Server** **`PluginRuntimeConfig.vue`**：**`watch(pluginId, load, { immediate: true })`** + **`useActivatedRefreshOnce(() => load())`**，`load` 内按快照 id 避免竞态。**OSS** **`PluginRuntime.vue`**（路由 **`keepAlive: true`**）：**`bootstrapPluginRuntime`**（进入前 **`clearStreamHealthAutoRefresh`**、`loadRuntimeConfig(bootstrapId)`、内置插件面板分支均用本次引导的 **`bootstrapId`**）、**`watch(pluginId)`** 与二次 **`onActivated`** 再引导，与详情页 keep-alive 策略一致（同样复用 **`useActivatedRefreshOnce`**）；各内置 **`fetch*`** 在请求返回后以 **`isCurrentRuntimePlugin(插件 id)`** 丢弃过期响应，避免快速切换运行中插件时旧数据写入表格；**`saveRuntimeConfig`**（**`PUT .../runtime/{id}/config`**）、**`triggerAlertChannelTest`**（**`POST .../alert-test`**）与「刷新运维数据」快捷动作在异步返回后比对 **`pluginId` 快照**，避免已离开该运行页仍更新成功提示或 Toast。 |
| **开发者/审核后台返回刷新**（Server） | ✅ | `PluginDeveloper.vue`、`MyPlugins.vue`、`AdminPluginReviews.vue`、`AdminPluginOfficialPublish.vue`、`PluginDocsAdmin.vue` 以及管理端目录页 `AdminPluginCatalog.vue` 已统一采用“激活刷新 + 竞态保护 + 刷新可见化”：接入 **`useActivatedRefreshOnce`**（首屏 `onMounted`，二次激活自动刷新）、列表加载函数使用 `seq` 请求快照（request sequence）避免旧请求覆盖新结果、头部展示“最近刷新时间”便于人工核对。`AdminPluginCatalog.vue` 的市场目录、快照状态/审计、兼容矩阵均已纳入该策略。相关状态与方法（`seq`、最近刷新时间、格式化 label）已统一抽为 **`useListRefreshState`**（含 `lastRefreshedLabel`），减少多页重复实现。 |
> 回归联动：服务器版盘点文档 **§6.3.1** 已新增 `P2-E2E-11`，专门覆盖上述管理端列表“二次激活自动刷新 + 防竞态写回 + 最近刷新时间可见化”验收。
| **`/plugins/app-version-check`** | ✅ | 仅针对 **`mobile_app_suite` / `mini_program_suite`** 的 **App 壳版本**，并支持灰度放量（`gray_device_allowlist` / `rollout_ratio` / `device_id`）。 |
| 更新保留业务数据 | ✅ | 新增 `HOOK_ON_UPGRADE`（常量 `on_upgrade`）作为“升级迁移入口”：在安装/升级完成后建表并触发该 Hook（在 `HOOK_ON_STARTUP` 前），插件可在回调里执行必要的 DDL/DML 以兼容旧数据。安装/升级响应已附带 `upgrade_hook_report`（`hook_name/operation/success/failed/timeouts/errors/strict_blocked`），并在 Hook 异常时写入审计动作 `plugin_upgrade_hook_warning`（`summary` 为结构化 JSON，便于统计与筛选；**OSS** 上传路径 JSON 内 `source=upload`，**Server** 另含 `marketplace` / `admin_zip`）。可通过 `PLUGIN_UPGRADE_HOOK_STRICT` 控制策略：默认 `false`（告警后继续），`true` 时升级阻断。**前端**：OSS 插件详情/插件中心在**商城安装**失败且响应为严格模式结构化 `detail` 时，会弹出 `upgrade_hook_report` JSON；商城安装请求带 `skipFriendlyMessage` 以免与全局 axios 兜底 Toast 重复。**OSS 超管**在插件中心与插件详情 **本地上传 zip** 同样带 `skipFriendlyMessage` 并弹报告（详情页上传的包 id 可与当前页插件不同；若与当前页 id 一致则安装成功后跳转运行页）。**Server** 用户侧插件详情（商城安装）与 **管理端插件管理**（本地上传 zip）均会 `getFriendlyError` + 弹报告。回归用例见服务器版盘点 **§6.3.1 P2-E2E-10**。 |

### 3.8 卸载

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| API `DELETE /api/v1/plugins/{plugin_id}` | ✅ | 删目录或单文件 `.py`、`_read_plugin_tables` → `DROP TABLE IF EXISTS`。 |
| 卸载前 Hook | ✅ | **`HOOK_ON_SHUTDOWN`** 后 **`HOOK_ON_UNINSTALL`**（`plugin_id=` 仅调度该插件注册的回调）；此前已 **合并** `plugin_manager.emit` 重复定义，保证 SIP Trace、vendor 隔离与 STARTUP 任务追踪、SHUTDOWN cancel 同一路径生效。 |
| 卸载后 `record-event` action=`uninstall` | ✅ | `_notify_server_plugin_event`。 |
| 前端确认框 | ✅ | `PluginCenter.vue` 卸载前调 **`GET .../{plugin_id}/uninstall-preview`**，在确认框中列出将 **`DROP` 的表名**（来自 `plugin.json.tables`）。 |
| 租户级运行时配置等残留 | ✅ | **OSS**：卸载时删除所有 **`plugin_runtime_config.{tenant}.{plugin_id}`** 行，并从内存 **`_runtime_plugin_config`** 去掉该 `plugin_id`。**Server**：从 **`system_settings.plugin_runtime_config`** JSON 中移除该插件键并同步内存。 |

---

## 4. 跨版本：许可证服务

| 细项 | 状态 | 实现说明 |
|------|------|----------|
| Ed25519 签名与校验 | ✅ | `verify_license_payload` / `sign_license_payload`（服务器版超管签发场景需私钥配置）。 |
| OSS 提供 `POST .../license/verify`、`.../license/sign` | 部分 | 路由上带 **`require_server_edition`** 依赖时，**仅服务器版**可用；OSS 构建若不启用 server edition 则这些端点不可用（避免 OSS 私自发证）。 |

---

## 5. 缺口汇总（便于排期）

### P0（安全/收入相关）

| 缺口 | 说明 |
|------|------|
| 包完整性校验 | ✅ **可选**：catalog 字段 **`package_sha256`** / **`sha256`** / **`packageSha256`**（64 位十六进制）；OSS **`POST .../marketplace/install`** 下载后校验，不一致则 400；**未填则不校验**（兼容旧条目）。**plugin.json manifest 签名**（Ed25519，**`PLUGIN_MANIFEST_*`**）可选；**整包 ZIP 二进制签名**可选：catalog 提供 `package_signature` 且配置 `PLUGIN_PACKAGE_ED25519_PUBLIC_KEY` 时，对下载后的 ZIP 做 Ed25519 验签（默认不强制，见 `PLUGIN_PACKAGE_SIGNATURE_REQUIRED`）。 |
| 运行时授权 | **OSS**：**`/plugins/runtime/*` + `plugin-assets`** **已购列表**校验（**超管**豁免）；可选 **`PLUGIN_PAID_RUNTIME_INSTALL_CHECK`** 对 paid **每次 runtime 请求** **`install-check`**；**`/menus` / mobile-entries** 同上；**安装** **`install-check` strict**；**付费 Hook** **`PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS`**；**`/purchased` 代理** 与 **`?token=`** 转发见 **§3.1**。**Server**：**`/menus`**、**`mobile-entries`**、**`GET/PUT runtime/{id}/config`**、**`GET .../plugin-assets/...`** 对 **paid** 与 **`/purchased`** 同源（**§3.4～3.6**）；此外，通用 runtime 表查询/导出类接口在 **Server** 场景下也会继续走已购校验（不再因 `APP_EDITION=server` 提前跳过），从而闭合此前“其余 `runtime/*` 业务路由可能未鉴权”的缺口。**全站非 plugins 路由** 等仍可补强。 |
| 服务器版订单风控 | **部分**：插件下单与 **提现申请** 已具备用户窗口 + IP（可选） + 设备指纹（可选）限流（见 **§2.3**），并已在管理员 **approve** 时对“可提现余额”做二次校验；其中可选基于结算成熟度（`BILLING_WITHDRAWAL_MIN_SETTLEMENT_AGE_SECONDS`）过滤结算收入、以及可选在创建提现时做 OTP/密码二次确认（`BILLING_WITHDRAWAL_CREATE_REQUIRE_SENSITIVE_CONFIRM`），降低刚支付后立即提现导致的套现风险；同时新增轻量级“账号风险画像”（近期提现被拒次数冻结：`BILLING_WITHDRAWAL_RISK_REJECTED_WINDOW_SECONDS` / `BILLING_WITHDRAWAL_RISK_REJECTED_BLOCK_COUNT`）与“支付链路画像”（按租户近期订单 `failed` 失败量/失败率冻结：`BILLING_WITHDRAWAL_RISK_ORDER_*`）；本次增强：在租户级未触发时，进一步按订单 `pay_channel` 分组做通道维度探测（同阈值复用，触发同一套 `block|review` 行为），以缩小“支付通道级异常图谱”的落地差距，并新增管理端按支付通道处置统计接口（`GET /api/v1/billing/withdrawals/risk-disposition-stats/by-pay-channel`）及通道×规则二维处置统计接口（`GET /api/v1/billing/withdrawals/risk-disposition-stats/by-pay-channel-by-rule`），用于观测通道维度误报/确认风险率。风控支持总开关与分规则开关（`BILLING_WITHDRAWAL_RISK_ENABLED`、`BILLING_WITHDRAWAL_RISK_REJECTED_BLOCK_ENABLED`、`BILLING_WITHDRAWAL_RISK_ORDER_PROFILE_ENABLED`）；命中动作支持 **`BILLING_WITHDRAWAL_RISK_HIT_ACTION=block|review`**：`block` 直接拒绝，`review` 则允许创建 `pending` 但会打上 `RISK_REVIEW_REQUIRED` 备注进入人工审核。命中会写入审计中心（`operation_audits`，`module=billing`、`action=withdrawal_risk_block_*|withdrawal_risk_review_*`），并可由管理员通过 `GET /api/v1/billing/withdrawals/risk-events` 查询（支持 `action/result/start_at/end_at` 过滤）；另外支持可选 webhook 告警（`BILLING_WITHDRAWAL_RISK_ALERT_WEBHOOK_URL`、`BILLING_WITHDRAWAL_RISK_ALERT_WEBHOOK_TIMEOUT_SECONDS`）。**运维闭环**：`risk_disposition` 多维度统计、**只读阈值建议**与 **预演**、**DB 持久化覆盖**（`system_settings.billing_withdrawal_risk_overrides`，与 env 合并并返回 **`diff_vs_env`**）、**apply** 与 **clear**（**DELETE** 或 **POST .../risk-threshold-overrides/clear**）、**dry_run 试算审计查询**（`GET /api/v1/billing/withdrawals/risk-threshold-preview-logs`），详见 **§6**。并实现跨租户风险资产追踪最小可用版本（基于 IP/设备指纹哈希命中聚合 + `user_id` 命中聚合 + 全局黑名单管理），用于识别跨租户高频风险资产；并提供可开关的自动封禁（基于 rate-limit 命中聚合阈值）。仍缺更精细的通道/渠道策略分层与更多追踪维度扩展。 |

**P0 缺口的改判口径（何时算“完成/可关闭”）**

- 包完整性校验：至少满足一种“可回归”的校验策略（`sha256` 校验 / manifest 签名 / ZIP 验签），并能给出失败时的稳定错误提示与可诊断证据（状态码 + 失败原因）。
- 运行时授权：`install-check` / runtime / assets / menus / mobile-entries 的 paid 过滤必须同源，并在 OSS/Server 两端回归用例中不出现“已购但被拦/未购但可用”的冲突。
- 服务器版订单风控：规则开关、命中动作、审计与运维覆盖（阈值预演、覆写、清除）均可执行；并能提供最小观测闭环（统计接口输出可用于评估误报/确认风险率）。

### P1（体验与规范）

| 缺口 | 说明 |
|------|------|
| 插件更新发现 | ✅ **`GET .../marketplace/update-summary`** + 开源插件中心角标（详见 **§3.7**）。 |
| 卸载 UX + `on_uninstall` Hook | ✅ **`HOOK_ON_UNINSTALL`** + 预览 API + 前端表名提示（详见 **§3.8**）；外部资源清理依赖插件实现。 |
| 表名前缀或命名空间 | **OSS + Server**：**可选强制**（`PLUGIN_TABLES_REQUIRE_PLUGIN_ID_PREFIX`）；Server 的 `POST /api/v1/plugins/validate-upload` 也会在开启时对 `plugin.json.tables` 进行前缀校验；同时新增 CI 扫描脚本（默认仅做表名合法性校验，严格前缀校验可在仓库 Variables 中打开）。 |

**P1 缺口的改判口径**

- 表名前缀/命名空间：当开启强制前缀时，上传校验 + CI + 安装/卸载全链路对同一规则一致；当关闭时，文档必须明确“不强制”的风险与约束（避免作者误以为强制）。

### P2（产品澄清）

| 缺口 | 说明 |
|------|------|
| OSS 超管本地上传 | **已澄清**：详见 **§1.1**（超管 `upload` = 自建分发，≠ 平台公开上架）。 |
| 退款策略 | **API**：`purchase_policy` + **`BILLING_PLUGIN_ORDER_REFUND_ELIGIBLE` / `BILLING_PLUGIN_ORDER_TERMS_NOTICE`**；**条款与状态机**仍须运营侧完备。 |

**P2 缺口的改判口径**

- 退款策略：API 字段含义与对外条款在文档中一致；并至少有 1 条端到端回归路径能证明“用户能看到规则 + 管理端能按规则处置（或明确声明暂不支持退款）”。

---

## 6. 附录：关键 API 一览（便于测试）

**服务器版鉴权（与 OSS iframe 对齐）**

- 除 **`Authorization: Bearer <jwt>`** 外，**`deps.get_current_user`** 支持 **`?token=<jwt>`**（query），供 **`plugin-assets` iframe**、无法在请求头带 Bearer 的场景使用；与 **`PluginRuntime.vue`** 内拼接的 **`token=`** 一致。

**服务器版（节选）**

- `GET /api/v1/plugins/marketplace/public` — 公共市场列表（OSS 拉取）。
- `POST /api/v1/plugins/marketplace/submissions` — 作者提交审核。
- `PUT /api/v1/plugins/marketplace/submissions/{id}/approve|reject` — 审核。
- `POST /api/v1/plugins/install-check` — 安装付费插件前预检（订阅；默认另需 **已购/套餐含**，否则 **403**，主路径 `detail.reason_code=PLUGIN_NOT_PURCHASED`，详见 **§2.3**）。
- `POST /api/v1/plugins/record-event` — 安装/卸载上报。
- `GET /api/v1/plugins/purchased` — 已购插件 id。
- `GET /api/v1/plugins/menus` — PC 侧栏；**paid** 非超管与 **`/purchased`** 同源；条目含 **`frontend_url`**。
- `GET /api/v1/plugins/marketplace/update-summary` — 已装版本 vs 市场 catalog（与 OSS 同路径）。
- `POST /api/v1/plugins/marketplace/install` — 市场安装（catalog 含 `package_sha256`/`sha256` 时校验 zip）；**付费**插件与 **`install-check` 同源** 订阅 + **`PLUGIN_INSTALL_CHECK_REQUIRE_ENTITLEMENT`** 权益校验。
- `POST /api/v1/plugins/upload` — **仅服务器版**、**管理员**本地上传 zip 安装/升级（`require_server_edition`）；管理后台 **插件管理** `AdminPluginCatalog.vue`（`/admin/plugin-catalog`）提供入口；升级 Hook 审计 `source=admin_zip`，严格模式与商城安装一致（`upgrade_hook_report` + 前端弹窗）。
- `GET /api/v1/plugins/{plugin_id}/uninstall-preview` — 卸载前将删除的 `tables` 列表。
- `GET|PUT /api/v1/plugins/runtime/{plugin_id}/config` — 移动端原生配置；**paid** 须租户权益（与 **`/purchased`** 同源），超管豁免。
- `GET /api/v1/plugins/plugin-assets/{plugin_id}/{asset_path}` — 插件包内静态页（与 OSS 路径一致）；**paid** 同上；默认 **`asset_path`** 为 **`index.html`**。
- `GET /api/v1/plugins/mobile-entries` — **paid** 过滤策略与上两项一致（租户权益 / 超管豁免）。
- `GET /api/v1/billing/payment/channels` — 已启用的官方微信/支付宝渠道与默认 `pay_channel`。
- `POST /api/v1/billing/payment/notify/wechat` | `.../alipay` — 支付异步通知（无需登录）。
- 计费与提现 — `/api/v1/billing/*`（见 `billing.py` 路由）；**§2.3**：`BILLING_PLUGIN_ORDER_*`（下单）、`purchase_policy`（订单响应与 `orders/me`）、`BILLING_WITHDRAWAL_*`（提现申请）。
- `GET /api/v1/billing/withdrawals/risk-events` — 管理员查看提现风控命中审计（`withdrawal_risk_block_*` 与 **`withdrawal_risk_review_*`**，支持 `action`（精确匹配）/`result`/`start_at`/`end_at`/`skip`/`limit`）。
- `GET /api/v1/billing/withdrawals?risk_only=true` — 管理员仅查看风控复核队列（`note` 含 `RISK_REVIEW_REQUIRED`）。
- `PUT /api/v1/billing/withdrawals/{id}/status` — 审核时可带 `risk_disposition=false_positive|confirmed_risk`，用于沉淀风险处置结果（写入 `note` 与审计摘要）。
- `GET /api/v1/billing/withdrawals/risk-disposition-stats` — 管理员查看风控处置统计（`false_positive_rate` / `confirmed_risk_rate`，支持 `start_at/end_at`）。
- `GET /api/v1/billing/withdrawals/risk-disposition-stats/by-rule` — 管理员查看按规则维度的处置统计（`rejected_count` / `payment_failed_count` / `payment_failed_rate`）。
- `GET /api/v1/billing/withdrawals/risk-disposition-stats/by-pay-channel` — 管理员查看按支付通道维度的处置统计（支持 `start_at/end_at`、`min_total`、`skip/limit`）。
- `GET /api/v1/billing/withdrawals/risk-disposition-stats/by-pay-channel-by-rule` — 管理员查看“支付通道 + 风控规则”二维处置统计（支持 `start_at/end_at`、`min_total`、`skip/limit`）。
- `GET /api/v1/billing/risk-assets/asset-suggestions` — 跨租户风险资产聚合建议（基于 `ip` / `device_fingerprint` / `user_id` / `plugin_id` rate-limit/黑名单命中，支持 `start_at/end_at`、`min_tenant_count`、`min_hits`、`skip/limit`；并返回自动封禁阈值是否已满足与 ETA 粗估）。
- `GET /api/v1/billing/risk-assets/blacklist` — 查看全局风险资产黑名单（基于 `ip` / `device_fingerprint` / `user_id` / `plugin_id` 命中）。
- `POST /api/v1/billing/risk-assets/blacklist` — 加入/更新全局风险资产黑名单（可选 `expires_seconds`、写审计）。
- `DELETE /api/v1/billing/risk-assets/blacklist` — 移除全局风险资产黑名单（`asset_type`/`asset_value`）。
- `GET /api/v1/billing/withdrawals/risk-disposition-stats/by-tenant` — 管理员查看按租户维度的处置统计（支持 `start_at/end_at`、`min_total`、`skip/limit`）。
- `GET /api/v1/billing/withdrawals/risk-disposition-stats/by-tenant-by-rule` — 管理员查看“租户 + 规则”二维处置统计（支持 `start_at/end_at`、`min_total`、`skip/limit`）。
- `GET /api/v1/billing/withdrawals/risk-threshold-suggestions` — 管理员查看只读阈值建议（按规则给出 `loosen/tighten/keep` 与建议值，不自动改配置，支持 `start_at/end_at/min_total`）。
- `POST /api/v1/billing/withdrawals/risk-threshold-simulate` — 管理员做候选阈值预演（只读、启发式估算，不改配置）。
- `GET /api/v1/billing/withdrawals/risk-threshold-overrides` — 管理员查看 DB 中 `billing_withdrawal_risk_overrides`、**env 默认值**、合并后的 **effective**，以及 **`diff_vs_env`**（每项是否仍等于 env、是否仍有 DB 键）。
- `POST /api/v1/billing/withdrawals/risk-threshold-apply` — 管理员将候选阈值写入 DB 覆盖（默认需 OTP/密码二次确认），并写审计；支持可选 `start_at/end_at/min_total`，以及 `dry_run=true`（仅返回预演与差异，不落库）；`dry_run` 下可按 `BILLING_WITHDRAWAL_RISK_DRY_RUN_AUDIT_ENABLED` 写 `preview` 审计。响应含 **`simulation_before_apply`**、**`env_defaults`**、**`effective`**、**`diff_vs_env`**；提现风控每次请求从 DB 合并，无需重启进程。
- `GET /api/v1/billing/withdrawals/risk-threshold-preview-logs` — 管理员分页查看 **dry_run 试算** 审计（`action=withdrawal_risk_threshold_preview`；依赖上述开关与 `dry_run=true`），支持 **`audit_result`**（对应审计记录 `result`）/`start_at`/`end_at`/`skip`/`limit`。
- `DELETE /api/v1/billing/withdrawals/risk-threshold-overrides` — 清除 DB 覆盖（body：`scope=all|rejected_count|payment_failed_count|payment_failed_rate`，需二次确认），`all` 清空整段 JSON；写审计 `withdrawal_risk_threshold_override_clear`。
- `POST /api/v1/billing/withdrawals/risk-threshold-overrides/clear` — 与上一项 **同行为**（兼容不支持 DELETE body 的客户端/网关）。

**开源版（节选）**

- `GET /api/v1/plugins/marketplace` — 市场列表（远程或本地）。
- `GET /api/v1/plugins/marketplace/update-summary` — 已装版本 vs 市场版本，返回 `has_update`。
- `POST /api/v1/plugins/marketplace/install` — 从市场安装（catalog 含 `package_sha256`/`sha256` 时校验 zip）。
- `POST /api/v1/plugins/upload` — 超管本地上传安装（非官方商城路径）；前端入口 **`PluginCenter.vue`** / **`PluginDetail.vue`**（仅当 JWT 中 `is_superuser` 为真时展示上传区），请求带 **`skipFriendlyMessage`** 并与 **`upgrade_hook_report`** 弹窗对齐。
- `GET /api/v1/plugins/{plugin_id}/uninstall-preview` — 卸载前将删除的 `tables` 列表。
- `DELETE /api/v1/plugins/{plugin_id}` — 卸载。
- `GET /api/v1/plugins/menus`、`GET /api/v1/plugins/installed`、`GET /api/v1/plugins/purchased`。
- `GET /api/v1/plugins/mobile-entries` — 移动端/小程序入口；**paid** 须已购（**`/purchased` 代理**），**超管**不过滤。
- **`/api/v1/plugins/runtime/*`**、**`GET .../plugin-assets/...`** — OSS 下若目标插件 **`type: paid`**，需已登录且（与 **`/purchased`** 一致）**已购**，超管豁免；可选 **`PLUGIN_PAID_RUNTIME_INSTALL_CHECK`** 对每次请求再 **`install-check`**；iframe 静态资源需 **`?token=`** 与 Bearer 同源策略配合（代理 **`/purchased`** 与 **`install-check`** 均支持 **`?token=`**）。

### 6.1 P2 双端购买授权回归清单（可执行）

> P2 当前统一结论（固定口径）：双端购买授权主链路已贯通，失败原因主路径已统一到结构化 `detail.reason_code`（`SUBSCRIPTION_EXPIRED` / `PLUGIN_NOT_PURCHASED`）；Server 前端主业务 `views` 及插件运营类 `components`（如 `PluginOfficialPublishManager`、`PluginRolloutManager`）已统一 `getFriendlyError` / `getApiErrorMessage`（`Login.vue` / `AdminLogin.vue` OTP/跨端跳转业务特判保留）；**OSS 前端主业务视图**已统一经 `getFriendlyError` / `getApiErrorMessage` 展示接口错误（`utils/ui.ts` 的 `buildErrorMessage` 同源，避免直读 `response.data.detail`）；主链 `catch` 已收窄为 `unknown`，部分列表/树仍保留 `ref<any>`；**OSS 登录页**保留 OTP 等字符串 `detail` 特判。插件/计费相关页（如 `BillingCenter`、`PluginRuntime` / `PluginPanels`、移动识别三页、`ReportPlaceholder`）与监控、电视墙、设备录像、电子地图、运维与审计等页面均已纳入同一套映射，当前阶段为“回归验收中”（详见 **§6.1**；改判条件见 **§6.1.3**）。
 
> 目标：作为“`回归验收中` -> `已完成`”改判前的最小验收集合。  
> 判定原则：每条用例都应满足“状态一致、失败原因清晰、下一步动作明确”。

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果（验收点） |
|------|------|----------|----------|--------------------|
| P2-E2E-01 | 未登录浏览与购买引导 | OSS 与 Server 公共商城可访问 | 在 OSS 插件中心与 Server 公共页分别打开同一付费插件详情，点击主按钮 | 双端均显示“需购买”语义；跳转到 Server 登录/购买路径一致；无歧义动作 |
| P2-E2E-02 | 登录后购买并回流安装 | 有可购买付费插件；租户订阅有效 | 在 Server 完成购买，使用回流入口返回 OSS 插件中心 | 同一插件在 OSS 显示“已购待装/可安装”；主按钮为“安装”；不再显示“去购买” |
| P2-E2E-03 | 订阅过期失败口径 | 构造订阅过期租户 | 在 OSS 执行安装预检或安装动作 | 返回 402 且 `detail.reason_code=SUBSCRIPTION_EXPIRED`；前端提示续费路径与动作一致 |
| P2-E2E-04 | 未购买失败口径 | 订阅有效但未购买该付费插件 | 在 OSS 执行安装预检或安装动作 | 返回 403 且 `detail.reason_code=PLUGIN_NOT_PURCHASED`；前端提示“去 Server 购买/续费” |
| P2-E2E-05 | 运行期授权拦截 | 未购买付费插件或撤销权益 | 直接访问 `runtime`/`plugin-assets` 入口 | 运行期失败与安装失败提示口径一致（原因+建议动作一致） |
| P2-E2E-06 | 登录态切换一致性 | 同一浏览器内切换账号（A 已购，B 未购） | 刷新 OSS 插件中心、详情页与运行入口 | 三处状态同步切换，不出现“旧账号状态残留” |
| P2-E2E-07 | 免费插件对照 | 选取免费插件 | 在 OSS 与 Server 公共页查看状态并执行安装 | 双端均表现为“可安装/安装”；不触发购买链路 |
| P2-E2E-08 | 废弃插件受限态 | 选取 `deprecated` 且禁用策略生效插件 | 在 OSS 与 Server 页面查看并尝试操作 | 双端均显示“受限/已废弃”语义；主动作不引导购买/安装 |
| P2-E2E-09 | Server 插件运营页失败提示 | 可登录 Server 管理端；能打开「官方发布管理」「灰度发布管理」等页（或同类插件运营入口） | 在任一运营页触发接口失败（如无权限、校验失败、服务端错误；可用 DevTools 模拟响应辅助） | 提示为可读文案（经 `getFriendlyError` / `getApiErrorMessage`）；不出现 `[object Object]` 或对结构化 `detail` 的错误直拼 |

**接口级核对（建议与上述 E2E 并行执行）**

- `POST /api/v1/plugins/install-check`：核对 402/403 时 `detail.reason_code`（`SUBSCRIPTION_EXPIRED` / `PLUGIN_NOT_PURCHASED`）。
- `POST /api/v1/plugins/record-event`：核对 402/403 失败输出与 `install-check` 同口径。
- `GET /api/v1/plugins/purchased`：购买后列表刷新时机与页面状态更新一致。
- `GET /api/v1/plugins/marketplace/update-summary`：已装/可更新状态与插件中心展示一致。
- `GET /api/v1/plugins/menus`、`GET /api/v1/plugins/mobile-entries`：paid 过滤与 `purchased` 同源，避免“菜单可见但运行失败”。

#### 6.1.1 P2 回归填报模板（可直接勾选）

| 用例 ID | 用例说明 | 结果（通过/失败/阻塞） | 证据（接口响应/页面截图/日志） | 备注 |
| --- | --- | --- | --- | --- |
| P2-E2E-01 | 未登录浏览与购买引导一致性（OSS/Server 同插件） | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-02 | 登录后购买并回流到 OSS 安装链路 | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-03 | 订阅过期失败口径（402 + `reason_code=SUBSCRIPTION_EXPIRED`） | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-04 | 未购买失败口径（403 + `reason_code=PLUGIN_NOT_PURCHASED`） | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-05 | 运行期授权拦截与安装期提示一致 | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-06 | 登录态切换后状态刷新一致（A 已购/B 未购） | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-07 | 免费插件双端动作一致（不误导到购买） | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-08 | 废弃插件受限态一致（不引导购买/安装） | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| P2-E2E-09 | Server 插件运营页失败提示（官方发布/灰度等，`getApiErrorMessage`） | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |

**接口级附加核对**

| 接口 | 核对点 | 结果（通过/失败/阻塞） | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| `POST /api/v1/plugins/install-check` | 402/403 均返回结构化 `detail.reason_code` | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| `POST /api/v1/plugins/record-event` | 402/403 失败输出与 install-check 同口径 | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| `GET /api/v1/plugins/purchased` | 购买后列表刷新与页面状态同步 | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| `GET /api/v1/plugins/marketplace/update-summary` | 已装/可更新状态与页面一致 | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |
| `GET /api/v1/plugins/menus` / `mobile-entries` | paid 过滤与 purchased 同源 | [ ] 通过 [ ] 失败 [ ] 阻塞 |  |  |

#### 6.1.2 接口验收样例（reason_code 主路径）

**预期错误体（订阅过期）**

```json
{
  "detail": {
    "reason_code": "SUBSCRIPTION_EXPIRED",
    "message": "当前租户订阅已到期，无法继续安装/使用付费插件",
    "suggestion": "请先在服务器版用户后台续费/恢复订阅后，再回到开源端重试",
    "retryable": false
  }
}
```

**预期错误体（未购买）**

```json
{
  "detail": {
    "reason_code": "PLUGIN_NOT_PURCHASED",
    "message": "未购买该付费插件或当前租户无授权",
    "suggestion": "请先在服务器版用户后台完成购买/续费，购买成功后回到开源端安装运行",
    "retryable": false
  }
}
```

**接口核对命令（示例）**

- `curl -X POST "$SERVER/api/v1/plugins/install-check" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"plugin_id\":\"your_paid_plugin\"}"`
- `curl -X POST "$SERVER/api/v1/plugins/record-event" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"plugin_id\":\"your_paid_plugin\",\"action\":\"install\"}"`

#### 6.1.3 最终验收执行顺序（建议）

> 目标：先验证“错误码主路径稳定”，再验证“用户全链路体验一致”。

1. **优先级 P0（先跑）**
   - `P2-E2E-03`（402 + `SUBSCRIPTION_EXPIRED`）
   - `P2-E2E-04`（403 + `PLUGIN_NOT_PURCHASED`）
   - 接口级：`install-check` / `record-event` 的 `detail.reason_code`
2. **优先级 P1（主链路）**
   - `P2-E2E-02`（购买 -> 回流 -> 安装）
   - `P2-E2E-05`（运行期拦截与安装期提示一致）
   - 接口级：`purchased` / `update-summary` 状态一致性
3. **优先级 P2（一致性与边界）**
   - `P2-E2E-06`（登录态切换）
   - `P2-E2E-01`（未登录引导一致）
   - `P2-E2E-07`（免费插件对照）
   - `P2-E2E-08`（废弃插件受限态）
   - `P2-E2E-09`（Server 插件运营页失败提示，可与 `menus` 核对并行）
4. **最终改判门槛**
   - 上述用例与接口核对项全部“通过”
   - 不存在“同一插件双端状态冲突”与“失败后下一步动作不明确”
   - **`P2-E2E-09`**：交付范围含 **Server 管理端插件运营页**（官方发布/灰度等）时必测并通过；若本次无该入口或账号权限，在清单「备注」标注 **N/A（环境与范围）**，并在含 Server 管理端的发布前补测或书面声明交付边界

#### 6.1.4 测试执行单页版（可直接贴任务系统）

**执行批次**

- `Batch-1（P0）`：`P2-E2E-03`、`P2-E2E-04`、`install-check`、`record-event`
- `Batch-2（P1）`：`P2-E2E-02`、`P2-E2E-05`、`purchased`、`update-summary`
- `Batch-3（P2）`：`P2-E2E-06`、`P2-E2E-01`、`P2-E2E-07`、`P2-E2E-08`、`P2-E2E-09`

**通过标准（每条都要满足）**

- 状态一致：同一插件在 OSS/Server 不冲突
- 原因清晰：失败时能看到稳定原因（优先 `detail.reason_code`）
- 动作明确：失败后有明确下一步（续费/购买/登录/返回安装）

**失败记录模板（复制即用）**

```text
[P2][FAIL] 用例ID:
- 场景:
- 实际结果:
- 期望结果:
- 接口证据: (URL/状态码/响应体)
- 页面证据: (页面路径/截图)
- 复现步骤:
- 影响范围: (OSS/Server/双端)
- 结论建议: (阻塞发布/可带风险发布)
```

**改判建议**

- `Batch-1~3` 全部通过后，将 P2 从“回归验收中”改判为“已完成”；**`P2-E2E-09`** 按 **§6.1.3「最终改判门槛」** 中 N/A 规则处理

#### 6.1.5 日报填报简版（每日复用）

> 说明：以下为**复制模板**。文档中出现的 `____-__-__`、`__`、`________` 均为“待填写字段”，用于你复制到任务系统/群公告/日报中再填写，**不要求**在本文正文内补齐。

```text
[P2 回归日报] 日期：____-__-__

一、批次结论
- Batch-1（P0）：通过 __ / 失败 __ / 阻塞 __；一句话结论：________
- Batch-2（P1）：通过 __ / 失败 __ / 阻塞 __；一句话结论：________
- Batch-3（P2）：通过 __ / 失败 __ / 阻塞 __；一句话结论：________
- P2-E2E-09（Server 插件运营页，见 §6.1.3 N/A 规则）：通过 __ / N/A __（N/A 原因：________）

二、今日新增问题（最多3条）
1) [用例ID] 现象：________；影响：________；责任侧：OSS/Server/双端
2) [用例ID] 现象：________；影响：________；责任侧：OSS/Server/双端
3) [用例ID] 现象：________；影响：________；责任侧：OSS/Server/双端

三、阻塞项（如无填“无”）
- 阻塞描述：________
- 需要支持：________
- 预计解除时间：________

四、改判状态
- 当前：回归验收中
- 距离“已完成”：剩余失败 __ 条，阻塞 __ 条
```

#### 6.1.6 周报汇总版（每周复用）

> 说明：以下为**复制模板**。文档中出现的 `____-__-__`、`__`、`________` 均为“待填写字段”，用于你复制到任务系统/群公告/周报中再填写，**不要求**在本文正文内补齐。

```text
[P2 回归周报] 周期：____-__-__ ~ ____-__-__

一、本周总体结论
- 总体状态：正常推进 / 有风险 / 阻塞
- 本周改动影响面：OSS / Server / 双端
- 是否建议改判“已完成”：否 / 是（满足条件：________）

二、批次通过率（按周累计）
- Batch-1（P0）：通过率 __%（通过 __ / 总数 __）
- Batch-2（P1）：通过率 __%（通过 __ / 总数 __）
- Batch-3（P2）：通过率 __%（通过 __ / 总数 __）
- P2-E2E-09：本周通过 __ 次 / N/A __ 次（与 §6.1.3 一致）

三、重复失败 Top3
1) [用例ID] 失败 __ 次；根因：________；责任侧：________；预计修复：____-__-__
2) [用例ID] 失败 __ 次；根因：________；责任侧：________；预计修复：____-__-__
3) [用例ID] 失败 __ 次；根因：________；责任侧：________；预计修复：____-__-__

四、风险与阻塞
- 风险1：________；缓解措施：________
- 风险2：________；缓解措施：________
- 阻塞项：________（无则填“无”）

五、下周计划
- P0：________
- P1：________
- P2：________
- 预计改判日期：____-__-__（如无法评估填“待定”）
```

#### 6.1.7 P2 对外同步口径（可直接复用）

- 双端购买授权主链路已贯通：服务器版购买、开源端识别、安装与运行校验已打通。
- 授权失败主路径已统一为结构化错误码：`detail.reason_code`（`SUBSCRIPTION_EXPIRED` / `PLUGIN_NOT_PURCHASED`）。**Server**：主业务 `views` 及插件运营类 `components`（如 `PluginOfficialPublishManager`、`PluginRolloutManager`）接口失败提示已统一为 `getFriendlyError` / `getApiErrorMessage`；**Server 登录页** `Login` / `AdminLogin` OTP 等特判保留。**OSS**：主业务 `views`/共享组件中的接口失败提示已统一为 `getFriendlyError` / `getApiErrorMessage`（含计费 `BillingCenter`、插件运行 `PluginRuntime` / `PluginPanels`、移动识别三页、`ReportPlaceholder`，以及监控中心、电视墙、设备录像、电子地图、地图源配置、运维与审计、移动指挥、云台辅助开关/雨刷等）；`editions/open-source/frontend/src` 主链 `catch` 已收窄为 `unknown`，部分列表/树仍保留 `ref<any>`；**OSS 登录页** OTP 等特判保留）。
- 当前阶段定义为 **回归验收中**，不再使用“部分完成”描述 P2。
- 改判规则明确：仅当回归清单（P0/P1/P2 批次 + 接口核对项）全部通过，且不存在“双端状态冲突/失败后无明确下一步动作”时，才改判为 **已完成**；**`P2-E2E-09`** 在交付含 Server 管理端插件运营能力时为必过项，否则按 **§6.1.3** N/A 说明记录。
- 已提供可执行资产：回归清单、执行顺序、单页测试模板、日报模板、周报模板，可直接用于测试排期与日常汇报。
- 工程侧：OSS / Server 前端 **`npm run build`** 已串联 **`check:no-raw-axios-detail`**（脚本 **`tools/frontend/check-no-raw-axios-detail.mjs`**，由各 `frontend/package.json` 调用），防止业务代码回退为直读 `response.data.detail`（`utils/errorMessage.ts` 与 `Login.vue` / `AdminLogin.vue` 除外）。仓库 **`.github/workflows/frontend-static-checks.yml`**（含 **`workflow_dispatch`** 手动触发）在变更涉及对应 `frontend` 目录时对上述检查（及 OSS 的 **`check:no-js-mirrors`**）做 CI 复跑，并新增 **类型检查步骤**：OSS 跑 **`npm run typecheck:ci`**（基于 `tsconfig.ci.json`，当前仅保留历史问题文件最小豁免），Server 跑全量 **`npm run typecheck`**。

### 6.2 其它文件索引

| 文件 | 说明 |
|------|------|
| `PLUGIN_SPEC.md` | 插件开发规范（开发者向）。 |
| `PLUGIN_OFFICIAL_AND_PAYMENT.md` | **重定向页（不再维护正文）**：官方标识/支付等口径已并入本文 **§0.1～§0.5**。 |
| `editions/server/docs/PAYMENT_SETUP.md` | 官方微信/支付宝商户配置与回调 URL（运维向）。 |
| `tools/frontend/check-no-raw-axios-detail.mjs` | 双端前端共用：禁止业务代码直读 `response.data.detail`（详见 **§6.1.7**）；可在各 `frontend` 目录执行，也可从仓库根执行并传入包根路径作为首参。 |
| `.github/workflows/frontend-static-checks.yml` | CI：OSS/Server 前端静态检查（可 **`workflow_dispatch`**）。 |

---

*文档结束。*
