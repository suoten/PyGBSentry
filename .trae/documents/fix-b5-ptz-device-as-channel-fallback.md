# 修复计划：B5-1~B5-4 PTZ 404 + stream/play/playback 同根因修复

## Context

第五轮审计发现 PTZ 控制端点返回 404 "Channel not found"，审计报告标注为"环境限制"。但深入调查发现**根因是代码缺陷**：代码库缺少 GB28181 标准要求的"设备即通道"(device-as-channel) 回退逻辑。

**GB28181 标准**：IPC 设备（类型 132）是单通道设备，`device_id == channel_id`。当设备注册后未完成 Catalog 同步时，系统无 `Resource`（通道）记录，导致所有依赖通道的端点返回 404。

**影响范围**（同根因）：
- B5-1~B5-4: PTZ 方向/变焦/预置位/巡航（审计报告已列出）
- `play_stream`、`playback_stream`（审计因 ZLM 未运行未触发，但代码路径相同）

**关键约束验证**：
- `StreamSession.resource_id` 无 FK 约束（`nullable=True`, `String(32)`)，可安全写入 `asset.id`
- `invite.py:2287` 仅检查 `resource_id` 非空，不校验 resources 表存在性
- 代码库已有 `SimpleNamespace` 替身模式（`stream_play.py:140-143`）

## 修复方案

在 5 个端点中添加 device-as-channel 回退：当 `Resource` 查询返回 None 时，检查 `channel_id == asset.gb_id`（IPC 设备），若匹配则用 `SimpleNamespace(id=asset.id, gb_id=asset.gb_id, name=asset.name)` 作为替身继续执行。

### 修改文件

#### 1. `backend/app/api/v1/endpoints/ptz.py`（3 个函数）

**`control_ptz`** (行 20-121):
- 行 36-51：当 `row` 为 None 时，增加 Asset 回退查询
- 回退：`select(Asset).where(Asset.gb_id == channel_id)` + 租户隔离
- 若找到 Asset，构造 `resource = SimpleNamespace(id=asset.id, gb_id=asset.gb_id, name=asset.name)`
- 后续 `sip_commander.send_ptz_cmd` 使用 `resource.gb_id`（= `asset.gb_id` = `channel_id`）

**`absolute_ptz`** (行 124-193) 和 **`control_preset`** (行 195-294)：
- 同 `control_ptz` 的回退模式

#### 2. `backend/app/api/v1/endpoints/stream/stream_play.py`（2 个函数）

**`play_stream`** (行 639-1262):
- 行 671-687：当 `resource` 为 None 时，检查 `channel_id == asset.gb_id`
- 若匹配，构造 `SimpleNamespace` 替身
- 后续所有 `resource` 使用（行 766/780/823/974/1201）安全：替身提供 `id` 和 `gb_id`

**`playback_stream`** (行 1271-1493):
- 行 1302-1305：当 `resource` 为 None 时，检查 `channel_id == asset.gb_id`
- 若匹配，构造 `SimpleNamespace` 替身
- 后续 `send_playback_invite`（行 1343）和 `_build_full_play_response`（行 1483）安全

### 回退逻辑模式（所有 5 个端点统一）

```python
from types import SimpleNamespace

# --- 原有 Resource 查询返回 None 后的回退 ---
# FIX: [2026-07-04] GB28181 IPC设备(类型132)的device_id==channel_id，
# 当设备未完成Catalog同步时无Resource记录，导致PTZ/预览/回放返回404。
# 回退：用设备自身作为通道（device-as-channel）。 [全栈工程师]
asset_fallback = select(Asset).where(Asset.gb_id == channel_id)
if not current_user.is_superuser:
    asset_fallback = asset_fallback.where(Asset.tenant_id == (current_user.tenant_id or "default"))
asset = (await db.execute(asset_fallback)).scalars().first()
if asset:
    resource = SimpleNamespace(
        id=asset.id,
        gb_id=asset.gb_id,
        name=asset.name,
    )
    # 继续执行，不返回 404
else:
    raise HTTPException(status_code=404, detail="Channel not found or no permission")
```

### 不修改的部分

- `hook.py` 自动拉流：ZLM hook 回调，仅在 ZLM 运行时触发，当前不影响功能
- `device_record.py`、`talk.py`、`record.py`：这些端点在 ZLM 运行后才会被调用，可后续按需修复
- `devices_channels.py`：通道列表查询，不影响 PTZ/预览功能

## 验证方案

1. **PTZ 验证**（ZLM 不需要）：
   - 发送 `POST /api/v1/ptz/{device_gb_id}/control?up_down=1&move_speed=50`
   - 预期：不再返回 404，返回 200 或 503（设备不可达，但 channel 查找通过）
   - 检查后端日志确认 SIP PTZ 指令已发送

2. **stream/play 验证**（需要 ZLM，可验证 channel 查找通过）：
   - 发送 `POST /api/v1/stream/play/{device_id}/{channel_id}`
   - 预期：不再返回 404 "Channel not found"，而是进入正常的 INVITE 流程（可能因 ZLM 未运行返回 503）

3. **回归测试**：
   - 确认已有通道的设备不受影响（正常 Resource 查询路径不变）
   - 确认不存在的 channel_id 仍返回 404

## 修复日志

生成 `《修复日志.md》`，记录 B5-1~B5-4 的 BUG 描述 → 根因分析 → 修复方案 → 验证结果。
