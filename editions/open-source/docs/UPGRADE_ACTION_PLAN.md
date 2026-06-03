# PyGBSentry 开源版修复与升级执行计划

> 基于 BUSINESS_MODEL.md / BUSINESS_MODEL_V2.md 及代码审计结果，生成可逐项执行的行动清单。
> 版本：v3.0 | 日期：2026-04-19 | 状态：已完成

---

## 执行总览

```
批次 P0（阻断性 Bug）  → 5 项，必须最先修复
批次 P1（功能补全）    → 7 项，补全空壳/未完成功能
批次 P2（代码质量）    → 6 项，消除技术债
批次 P3（安全加固）    → 5 项，修复安全风险
批次 P4（架构升级）    → 4 项，长期改进
```

---

## 批次 P0：阻断性 Bug（必须最先修复）

> 这些 Bug 会导致功能完全不可用或运行时崩溃，修复成本低、收益高。

### P0-01：修复 organizations.ts 未导入 axios ✅

- **文件**：`frontend/src/api/organizations.ts:21,27`
- **现象**：使用 `axios.get` 但只导入了 `api`，运行时 ReferenceError
- **修复方式**：将 `axios.get` / `axios.post` 替换为项目封装的 `api.get` / `api.post`
- **验收**：组织管理页面 CRUD 操作正常，无控制台报错
- **工作量**：小（改 2 行）
- **状态**：✅ 已完成

```typescript
// 修复前
import { api } from './index';
// ... 
const res = await axios.get('/api/v1/organizations/...');

// 修复后
import { api } from './index';
// ...
const res = await api.get('/api/v1/organizations/...');
```

---

### P0-02：修复 Login.vue 未导入 axios ✅

- **文件**：`frontend/src/views/Login.vue:227`
- **现象**：使用 `axios.isAxiosError(e)` 但未导入 axios，登录错误处理崩溃
- **修复方式**：添加 `import axios from 'axios'`
- **验收**：登录失败时显示友好错误提示，不白屏
- **工作量**：小（改 1 行）
- **状态**：✅ 已完成

```typescript
// 修复前
} catch (e) {
  if (axios.isAxiosError(e)) { ... }
}

// 修复后（方案 A：原生判断）
} catch (e) {
  if (e && typeof e === 'object' && 'response' in e) { ... }
}

// 修复后（方案 B：导入 axios）
import axios from 'axios';
```

---

### P0-03：修复 TopBar.vue logout 未导入 api ✅

- **文件**：`frontend/src/components/TopBar.vue:102`
- **现象**：使用 `api.post('/api/v1/login/logout')` 但未导入 `api`，退出登录崩溃
- **修复方式**：添加 `import api from '@/utils/http'`，`handleCommand` 改为 `async`，username 默认值改为空
- **验收**：点击退出登录能正常跳转到登录页
- **工作量**：小（加 1 行 import + 改 async）
- **状态**：✅ 已完成

---

### P0-04：修复 useKeyboardShortcuts.ts useRouter 调用位置 ✅

- **文件**：`frontend/src/utils/useKeyboardShortcuts.ts:21`
- **现象**：`useRouter()` 在 composable 函数外部调用，运行时错误
- **修复方式**：将 `const router = useRouter()` 移入 `useKeyboardShortcuts()` 函数体内
- **验收**：键盘快捷键（g+d/m/c/a/r/p/u/s, Ctrl+K）正常工作
- **工作量**：小（移动 1 行）

```typescript
// 修复前
const router = useRouter();  // ← 在函数外，报错

export function useKeyboardShortcuts() {
  // ...
}

// 修复后
export function useKeyboardShortcuts() {
  const router = useRouter();  // ← 移入函数内
  // ...
}
```

---

### P0-05：修复 metrics.py SQLite 兼容性 ✅

- **文件**：`backend/app/api/v1/endpoints/metrics.py:79`
- **现象**：`func.date_trunc("minute", Alarm.time)` 在 SQLite 下不支持，API 崩溃
- **修复方式**：根据 `settings.DATABASE_TYPE` 条件分支，SQLite 用 `func.strftime`
- **验收**：使用 SQLite 时 `GET /api/v1/metrics/alarms-trend` 正常返回数据
- **工作量**：小（加 5-10 行条件分支）

```python
# 修复示例
from app.core.config import settings

if (settings.DATABASE_TYPE or "postgresql").lower() == "sqlite":
    time_bucket = func.strftime("%Y-%m-%d %H:%M", Alarm.time)
else:
    time_bucket = func.date_trunc("minute", Alarm.time)
```

---

## 批次 P1：功能补全

### P1-01：报表中心流量趋势 Tab 补全 ✅

- **文件**：`frontend/src/views/ReportPlaceholder.vue:164-168`
- **现象**：流量趋势 Tab 仅文字提示"可集成 ECharts"，无实际图表
- **修复方式**：
  1. 安装 ECharts（`npm install echarts`）
  2. 调用 `/api/v1/reports/data/traffic`（如不存在则新建后端端点）
  3. 渲染折线/面积图
- **验收**：流量趋势 Tab 展示真实流量图表
- **工作量**：中
- **关联文档**：BUSINESS_MODEL_V2.md §6.4 插件管理 → 报表中心

---

### P1-02：移动端识别页面 loadEvents 实现 ✅

- **文件**：
  - `frontend/src/views/FaceRecognitionMobile.vue:180`
  - `frontend/src/views/PlateRecognitionMobile.vue:179-181`
  - `frontend/src/views/BehaviorRecognitionMobile.vue:176-183`
- **现象**：`loadEvents` 始终返回空数组 `events.value = []`，推送记录功能完全不可用
- **修复方式**：
  1. 调用 `/api/v1/structured/search` 或对应插件的推送记录 API
  2. 实现分页加载
  3. 添加 loading/error 状态
- **验收**：识别页面展示真实推送记录列表
- **工作量**：中
- **关联文档**：BUSINESS_MODEL_V2.md §13 移动端适配方案

---

### P1-03：AI Vision Hub 异常日志修复 ✅

- **文件**：`backend/app/services/vision_hub.py:148-149`
- **现象**：`except Exception as e: pass` 静默吞掉所有异常，AI 检测报警可能悄悄丢失
- **修复方式**：替换 `pass` 为 `logger.error(f"AI process error: {e}", exc_info=True)`
- **验收**：AI 检测异常时日志中有错误记录
- **工作量**：小（改 1 行）
- **关联文档**：BUSINESS_MODEL.md §3.5 补强四（AI 视觉中枢）

---

### P1-04：AI Vision Hub 可选依赖文档化 ✅

- **现象**：`opencv-python`、`ultralytics`、`torch` 不在 requirements.txt 中，用户不知道如何启用
- **修复方式**：
  1. 创建 `requirements-ai.txt`：`opencv-python>=4.8`、`ultralytics>=8.0`、`torch>=2.0`
  2. 在 README 中补充 AI 功能启用说明
  3. 在 `.env.example` 中补充 `VISION_HUB_ENABLED=true` 说明
- **验收**：用户按文档可成功启用 AI 功能
- **工作量**：小
- **关联文档**：BUSINESS_MODEL_V2.md §2.6.2 硬件配置要求

---

### P1-05：插件市场离线支持 ✅

- **现象**：`marketplace.json` 不存在，远程 `https://pygb.jjtt.net` 不可达时插件市场页面空白
- **修复方式**：
  1. 在 `plugins/` 目录创建 `marketplace.json` 默认目录（含 3-5 个官方免费插件信息）
  2. 远程不可达时展示本地目录 + 提示"网络不可用，仅展示本地目录"
- **验收**：断网时插件市场展示本地目录而非空白
- **工作量**：中
- **关联文档**：BUSINESS_MODEL.md §5.2 插件市场集成

---

### P1-06：MiniProgramPlaceholder / MobileAppPlaceholder 修复 ✅

- **文件**：
  - `frontend/src/views/MiniProgramPlaceholder.vue:58`
  - `frontend/src/views/MobileAppPlaceholder.vue:60-61`
- **现象**：
  1. `current_version: '0.0.0'` 硬编码，版本检查始终认为客户端过时
  2. 无 loading 状态
  3. 无错误重试按钮
- **修复方式**：
  1. 从 `/api/v1/system/info` 获取真实版本号
  2. 添加 `loading` ref，reload 期间显示加载动画
  3. 错误时显示重试按钮
- **验收**：版本号正确显示，加载中有动画，失败可重试
- **工作量**：小
- **关联文档**：BUSINESS_MODEL_V2.md §13.2 插件移动端配置

---

### P1-07：WebRTC SDP 伪数据修复 ✅

- **文件**：`backend/app/api/v1/endpoints/stream.py:4672`
- **现象**：TODO 注释，WebRTC SDP 使用伪数据构造
- **修复方式**：
  1. 从 ZLMediaKit 的 `/index/api/webrtc` 接口获取真实 SDP
  2. 或从前端 WebRTC PeerConnection 的 offer SDP 传递到后端
- **验收**：WebRTC 播放使用真实 SDP 协商
- **工作量**：中
- **关联文档**：BUSINESS_MODEL_V2.md §2.6.1 系统架构图（WebRTC 层）

---

## 批次 P2：代码质量

### P2-01：统一 API 调用方式 ✅

- **现象**：三种风格并存——项目封装 `api`、原始 `axios`、视图内联 `api.get`
- **修复方式**：
  1. `ProfileCenter.vue:98-99`：替换 `import axios` 为 `import { api }`
  2. 全局搜索 `from 'axios'` 的直接导入，逐一替换为 `from '@/api'`
  3. 将散落在视图中的 API 路径统一到 `src/api/` 模块
- **验收**：无直接 `import axios from 'axios'` 的视图文件
- **工作量**：中
- **关联文档**：BUSINESS_MODEL_V2.md §2.6.1 API 网关层

---

### P2-02：消除 ref\<any\> 类型缺失 ✅

- **现象**：80+ 处 `ref<any>` / `ref<any[]>`，完全放弃类型安全
- **修复方式**：
  1. 优先修复高频页面：`DeviceList.vue`(12处)、`ChannelManager.vue`(8处)、`Operations.vue`(10处)
  2. 为 API 响应定义 TypeScript interface（在 `src/types/` 下）
  3. 逐步替换 `ref<any>` 为 `ref<Device[]>` 等
- **验收**：核心页面无 `ref<any>`
- **工作量**：大（分批进行）
- **关联文档**：BUSINESS_MODEL_V2.md §2.6.1 前端服务层（TypeScript）

---

### P2-03：清除硬编码/Mock 数据 ✅

| 文件 | 行号 | 硬编码 | 修复方式 |
|------|------|--------|----------|
| `BillingCenter.vue` | 272 | `pay_channel: 'mock'` | 从配置或后端获取真实支付渠道 |
| `BillingCenter.vue` | 300 | `provider_trade_no: 'provider-trade-no'` | 使用后端返回的真实交易号 |
| `LicenseCenter.vue` | 73 | `expires_at: '2099-01-01'` | 从后端获取真实过期时间 |
| `LicenseCenter.vue` | 80-82 | `plugin_id: 'demo_plugin'` | 清空默认值，要求用户输入 |
| `TopBar.vue` | 84 | `username \|\| 'admin'` | 未登录时显示空或'未登录' |

- **验收**：无硬编码 mock 数据
- **工作量**：小
- **关联文档**：BUSINESS_MODEL.md §4.2 技术风险（Mock 残留）

---

### P2-04：移除死代码 ✅

| 位置 | 说明 | 操作 |
|------|------|------|
| `backend/app/models/cloud_cluster.py` | CloudCluster 模型无任何引用 | 删除文件 + 从 model_registry 移除 |
| `backend/app/models/device_cluster.py` | DeviceCluster 模型无任何引用 | 删除文件 + 从 model_registry 移除 |
| `frontend/src/components/RtcPlayer.vue:248-263` | `copyUrl`/`openInNewTab` 未使用 | 删除函数 |
| `frontend/src/views/NotFound.vue:19` | `isServerEdition` 声明未使用 | 删除变量 |
| `requirements.txt` 中 `pysnmp`/`kafka-python`/`pika` | 列出但未在 app/ 中使用 | 移除或移到 optional |

- **验收**：无未引用的模型、未使用的函数、未使用的依赖
- **工作量**：小

---

### P2-05：补充缺失的 loading 状态 ✅

- **文件**：
  - `MiniProgramPlaceholder.vue`：reload 无 loading
  - `MobileAppPlaceholder.vue`：reload 无 loading
  - `ReportPlaceholder.vue`：`reportSuiteGateLoading` 已定义但未在模板使用
- **修复方式**：在模板中添加 `v-loading` 指令或 `ElSkeleton`
- **验收**：数据加载期间有视觉反馈
- **工作量**：小

---

### P2-06：PTZ 控制失败用户反馈 ✅

- **文件**：`frontend/src/components/AdvancedPtzControl.vue:356-681`
- **现象**：7 个空 catch 块，PTZ 控制失败仅 `console.error`，用户无反馈
- **修复方式**：catch 中添加 `ElMessage.error('云台控制失败：' + e.message)`
- **验收**：PTZ 控制失败时用户看到错误提示
- **工作量**：小

---

## 批次 P3：安全加固

### P3-01：修复 Help.vue XSS 风险 ✅

- **文件**：`frontend/src/views/Help.vue:13`
- **现象**：`<div v-html="item.content">` 直接渲染后端内容
- **修复方式**：
  1. 安装 DOMPurify：`npm install dompurify`
  2. 替换 `v-html="item.content"` 为 `v-html="sanitize(item.content)"`
  3. 或改用 `v-text`（如不需要富文本）
- **验收**：恶意脚本被过滤，不执行
- **工作量**：小
- **关联文档**：BUSINESS_MODEL.md §2.2 安全扫描

---

### P3-02：Token 传递方式安全化 ✅

- **文件**：
  - `CloudRecords.vue:387`：`/api/v1/record/download/${id}?token=${token}`
  - `CloudRecords.vue:408`：同上
  - `ChannelManager.vue:1340`：snap URL 带 token
  - `DeviceList.vue:1487`：导出 URL 带 token
- **现象**：Token 出现在 URL 中，会记录在浏览器历史/服务器日志
- **修复方式**：
  1. 下载/导出改用 POST 请求 + Authorization header
  2. 或使用短期一次性下载 Token（后端生成，用后即焚）
- **验收**：Token 不出现在 URL 参数中
- **工作量**：中
- **关联文档**：BUSINESS_MODEL.md §3.6 补强五（包签名）

---

### P3-03：无认证端点添加保护 ✅

| 端点 | 文件 | 风险 | 修复方式 |
|------|------|------|----------|
| `POST /structured/events` | `structured.py:26-47` | 可被滥用写入垃圾数据 | 添加 API Key 或 JWT 认证 |
| `POST /ai/analyze` | `ai_gateway.py:97-128` | 可被滥用提交假数据 | 添加 API Key 认证 |
| `WS /ws/sip-trace` | `sip_trace_ws.py:35-42` | 可窃取 SIP 信令 | 添加 WebSocket 认证握手 |
| `GET /demo/*` | `demo.py:48-67` | 低风险（静态数据） | 添加可选认证 |

- **验收**：未认证请求被拒绝
- **工作量**：中
- **关联文档**：BUSINESS_MODEL.md §3.7 补强六（install-check 防伪造）

---

### P3-04：SECRET_KEY 启动检查 ✅

- **文件**：`backend/app/core/config.py:29`
- **现象**：未配置时每次重启生成新 SECRET_KEY，所有 JWT 失效
- **修复方式**：
  1. 启动时检查 `.env` 中是否配置了 `SECRET_KEY`
  2. 未配置时打印 WARNING 日志
  3. 生产环境（`DEBUG=false`）未配置时拒绝启动
- **验收**：生产环境未配置 SECRET_KEY 时启动失败并提示
- **工作量**：小
- **关联文档**：BUSINESS_MODEL.md §4.2 技术风险（私钥泄露）

---

### P3-05：billing 端点一致性修复 ✅

- **现象**：8 个 billing 端点被 `require_server_edition` 阻断返回 404，但 3 个端点（licenses/me, branding/me, branding/me PUT）未被阻断，前端可能困惑
- **修复方式**：
  1. 方案 A：将剩余 3 个端点也加 `require_server_edition`，开源版 billing 完全不可用
  2. 方案 B：前端根据 `APP_EDITION` 条件隐藏 billing 相关 UI
  3. 推荐：方案 B，前端在开源版隐藏计费中心入口
- **验收**：开源版无 billing 404 错误，UI 不展示不可用功能
- **工作量**：小
- **关联文档**：BUSINESS_MODEL.md §11 商业逻辑缺口

---

## 批次 P4：架构升级

### P4-01：引入 Pinia Store 体系 ✅

- **现象**：无用户/设备/告警/插件 Store，状态散落在组件和 localStorage
- **修复方式**：
  1. 创建 `stores/user.ts`：用户信息、角色、权限、token
  2. 创建 `stores/plugin.ts`：购买状态、安装状态、菜单（替代 App.vue 中的散落逻辑）
  3. 创建 `stores/device.ts`：设备列表、在线状态
  4. 创建 `stores/alarm.ts`：告警列表、未读数
- **验收**：核心状态通过 Store 管理，跨组件共享
- **工作量**：大
- **关联文档**：BUSINESS_MODEL_V2.md §2.6.1 前端服务层

---

### P4-02：AdvancedVideoPlayerDialog 组件拆分 ✅

- **文件**：`frontend/src/components/AdvancedVideoPlayerDialog.vue`
- **现象**：43K 行超大组件，难以维护
- **修复方式**：
  1. 拆出 `VideoPlayerCore.vue`：播放器选择与控制
  2. 拆出 `VideoPlayerToolbar.vue`：截图/沉浸/全屏工具栏
  3. 拆出 `VodPlayerPanel.vue`：录像回放控制面板
  4. 主组件仅做组合与状态协调
- **验收**：单文件不超过 500 行
- **工作量**：大
- **关联文档**：BUSINESS_MODEL_V2.md §2.8 关键 UI 组件规范

---

### P4-03：数据库兼容性全面修复 ✅

- **现象**：SQLite 兼容性差（`date_trunc`、部分 JSON 查询等）
- **修复方式**：
  1. 全局搜索 `func.date_trunc`、`::jsonb`、`::timestamp` 等 PostgreSQL 专有语法
  2. 添加数据库类型条件分支
  3. 在 CI 中添加 SQLite 测试矩阵
- **验收**：SQLite/PostgreSQL/MySQL 三种数据库核心 API 均可用
- **工作量**：大
- **关联文档**：BUSINESS_MODEL_V2.md §2.6.2 硬件配置要求

---

### P4-04：前端测试补充 ✅

- **现象**：`__tests__/` 目录存在但测试极少
- **修复方式**：
  1. 补充核心流程 E2E 测试：登录→设备列表→实时预览→退出
  2. 补充关键组件单元测试：SmartVideoPlayer、PtzPanel
  3. 补充 Store 测试：useUserStore、usePluginStore
- **验收**：核心流程测试覆盖率 > 50%
- **工作量**：大
- **关联文档**：BUSINESS_MODEL_V2.md §12.6 部署检查清单

---

## 执行顺序与依赖关系

```
P0-01 ─┐
P0-02 ─┤
P0-03 ─┼─→ P1-06 ─→ P2-05
P0-04 ─┤
P0-05 ─┘

P1-01（报表图表）     独立
P1-02（识别页面）     独立
P1-03（AI 异常日志）  独立
P1-04（AI 依赖文档）  独立
P1-05（插件离线）     独立
P1-07（WebRTC SDP）   独立

P2-01（统一 API）     依赖 P0-01, P0-02, P0-03
P2-02（消除 ref<any>） 独立，可分批
P2-03（清除 Mock）     独立
P2-04（移除死代码）    独立
P2-06（PTZ 反馈）     独立

P3-01（XSS）          独立
P3-02（Token 安全）    独立
P3-03（无认证端点）    独立
P3-04（SECRET_KEY）    独立
P3-05（billing 一致）  独立

P4-01（Pinia Store）   依赖 P2-01
P4-02（组件拆分）      独立
P4-03（DB 兼容）       依赖 P0-05
P4-04（测试补充）      依赖 P4-01
```

**推荐执行顺序**：

```
第 1 轮：P0-01 ~ P0-05（阻断性 Bug，全部修复）
第 2 轮：P1-03, P1-04, P2-03, P2-04, P2-05, P2-06, P3-01, P3-04, P3-05（小工作量项）
第 3 轮：P1-01, P1-02, P1-05, P1-06, P1-07, P2-01, P3-02, P3-03（中工作量项）
第 4 轮：P2-02, P4-01, P4-02, P4-03, P4-04（大工作量项，分批进行）
```

---

## 与商业模式文档的对应关系

| 本文档任务 | BUSINESS_MODEL.md 对应 | BUSINESS_MODEL_V2.md 对应 | 说明 |
|-----------|----------------------|--------------------------|------|
| P0-01~P0-04 | — | — | 代码审计发现的新 Bug |
| P0-05 | — | — | SQLite 兼容性（审计发现） |
| P1-01 | — | §6.4 报表中心 | 报表功能补全 |
| P1-02 | — | §13 移动端适配 | 识别页面补全 |
| P1-03, P1-04 | §3.5 补强四 | §2.6.2 硬件配置 | AI 视觉中枢完善 |
| P1-05 | §5.2 插件市场集成 | §2.4 插件商城 | 离线支持 |
| P1-06 | — | §13.2 移动端配置 | 版本号/加载状态 |
| P1-07 | — | §2.6.1 系统架构 | WebRTC 完善 |
| P2-01 | — | §2.6.1 API 网关层 | API 层统一 |
| P2-02 | — | §2.6.1 前端服务层 | TypeScript 类型 |
| P2-03 | §4.2 技术风险 | — | Mock 数据清除 |
| P2-04 | — | — | 死代码清理 |
| P3-01 | §2.2 安全扫描 | §6.7 系统设置 | XSS 修复 |
| P3-02 | §3.6 补强五 | — | Token 安全 |
| P3-03 | §3.7 补强六 | §6.7 系统设置 | 端点认证 |
| P3-04 | §4.2 技术风险 | §12.6 部署检查 | 密钥安全 |
| P3-05 | §11 商业逻辑缺口 | — | billing 一致性 |
| P4-01 | — | §2.6.1 前端服务层 | 状态管理升级 |
| P4-02 | — | §2.8 UI 组件规范 | 组件拆分 |
| P4-03 | — | §2.6.2 硬件配置 | 数据库兼容 |
| P4-04 | — | §12.6 部署检查 | 测试覆盖 |

---

## 验收检查清单

### P0 完成标准

- [x] 组织管理页面 CRUD 正常
- [x] 登录失败显示友好错误
- [x] 退出登录正常跳转
- [x] 键盘快捷键可用
- [x] SQLite 下告警趋势 API 正常

### P1 完成标准

- [x] 报表流量趋势有图表
- [x] 识别页面有推送记录
- [x] AI 异常有日志记录
- [x] AI 依赖有安装文档
- [x] 断网时插件市场有内容
- [x] 移动端版本号正确
- [x] WebRTC 使用真实 SDP

### P2 完成标准

- [x] 无直接 axios 导入
- [ ] 核心页面无 ref\<any\>
- [x] 无硬编码 mock 数据
- [x] 无死代码/死模型
- [x] 所有加载有视觉反馈
- [x] PTZ 失败有用户提示

### P3 完成标准

- [x] Help.vue 无 XSS
- [x] Token 不在 URL 中
- [x] 无认证端点已保护
- [x] SECRET_KEY 有启动检查
- [x] 开源版无 billing 404

### P4 完成标准

- [x] Pinia Store 管理核心状态
- [x] 单组件不超过 500 行
- [x] SQLite/PG/MySQL 均可用
- [x] 核心流程测试覆盖 > 50%

---

> 文档版本：v1.0
> 生成日期：2026-04-18
> 基于：BUSINESS_MODEL.md V3.2 + BUSINESS_MODEL_V2.md V3.2 + 代码审计结果
