# SIP_TRACE 事件字典（开源版）

本文档用于说明后端 `SIP_TRACE` 结构化日志事件，便于按 `event` 与 `trace_id` 联调 GB28181/SIP。

> 单一数据源：`app/sip/trace_events.py`  
> `GET /api/v1/system-config/sip-trace-events` 与本文档均基于该事件字典维护。

## 开关与采样

- 配置文件：`editions/open-source/backend/.env`
- 开启调试：
  - `SIP_DEBUG_TRACE_ENABLED=true`
- 采样率（0.0~1.0）：
  - `SIP_TRACE_SAMPLE_RATE=1.0`

说明：`SIP_TRACE` 默认脱敏敏感字段（如 Authorization 里的 nonce/response/cnonce）。

## 关键字段

- `event`: 事件名
- `trace_id`: 追踪 ID（优先使用 SIP `Call-ID`）
- 其他字段：按事件携带（如 `gb_id`、`platform_id`、`proto`、`addr`、`batch_idx`）

## 事件清单

### 接收侧（`app/sip/handlers.py`）

- `register_received`
  - 收到 REGISTER 请求
- `register_401_challenge`
  - 返回 401 Digest challenge
- `register_auth_failed`
  - Digest response 比对失败
- `register_ok_platform`
  - 识别为平台注册并 200
- `register_ok_device`
  - 识别为设备注册并 200
- `message_received`
  - 收到 MESSAGE 请求
- `message_keepalive_platform`
  - 收到平台 Keepalive 并更新在线时间
- `message_keepalive_unknown`
  - 收到未知来源 Keepalive
- `message_catalog_query_ack`
  - 收到 Catalog Query 并先回复 200
- `message_catalog_query_push`
  - Catalog Query 命中平台后触发目录回推
- `message_catalog_response`
  - 收到 Catalog Response 并进入解析
- `message_record_info`
  - 收到 RecordInfo 并进入解析
- `message_alarm`
  - 收到 Alarm 并进入处理
- `message_mobile_position`
  - 收到 MobilePosition 并进入处理
- `message_fallback_200`
  - 其他 MESSAGE 分支统一回复 200
- `catalog_push_start`
  - 准备向平台注册方回推目录
- `catalog_push_message`
  - 回推目录的某个 MESSAGE 批次

### 主动级联侧（`app/services/platform_service.py`）

- `platform_response_received`
  - 收到上级平台对 REGISTER 的响应
- `platform_register_sent`
  - 向上级平台发送 REGISTER
- `platform_keepalive_sent`
  - 向上级平台发送 Keepalive
- `platform_keepalive_ack`
  - 收到上级平台对 Keepalive 的 200 响应并刷新在线时间
- `platform_keepalive_miss_re_register`
  - Keepalive 连续无 ACK 达阈值后触发重注册
- `platform_catalog_sent`
  - 向上级平台发送 Catalog 批次

### 设备命令侧（`app/sip/commander.py`）

- `device_catalog_query_sent`
  - 向设备发送 Catalog Query
- `device_mobile_position_subscribe_sent`
  - 向设备发送 MobilePosition SUBSCRIBE
- `device_time_sync_sent`
  - 向设备发送 TimeSync

### PTZ 侧（`app/sip/ptz.py`）

- `device_ptz_sent`
  - 下发 PTZ 控制
- `device_ptz_preset_sent`
  - 下发 PTZ 预置位调用

## 联调建议

1. 先按 `trace_id` 聚合同链路日志（注册 -> challenge -> 注册成功 -> keepalive -> catalog）。
2. 再按 `event` 过滤，确认是否卡在某一跳（例如只有 `message_catalog_query_ack`，没有 `message_catalog_query_push`）。
3. 若抓包联动，优先比对 `Call-ID` 与 `X-Trace-ID`（两者通常一致）。

## 常见排障模式

- 注册成功但无目录：
  - 检查是否有 `message_catalog_query_ack` / `message_catalog_query_push`
  - 检查是否有 `catalog_push_message` 或 `platform_catalog_sent`
- 在线状态抖动：
  - 检查是否持续出现 `message_keepalive_platform`
- 鉴权失败：
  - 检查 `register_401_challenge` 与 `register_auth_failed` 的先后关系

