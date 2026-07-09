"""
GB28181 设备目录查询模块
"""
from app.sip.message import SipMessage
from xml.sax.saxutils import escape as _xml_escape
from app.core.config import settings, sip_host_for_contact
from app.sip.sn import next_sn  # P2-2: 统一 SN 生成策略
from app.core.xml_utils import parse_xml, get_xml_text, find_child, find_children
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.platform import ParentPlatform
from app.models.resource import Resource
from app.services.commercial_guard import check_channel_quota
from app.core.plugin_manager import plugin_manager, HOOK_ON_SIP_SEND
from app.sip.catalog_runtime import patch_device_catalog_runtime, utc_now_iso
from app.sip.send import send_sip_bytes
import secrets
from sqlalchemy import select, delete
from app.core.redis import redis_client
from loguru import logger  # 统一使用 loguru 替代 logging
import asyncio
import json
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务


_catalog_agg: dict[tuple[str, str], dict] = {}
_catalog_agg_ttl_seconds = 600
_catalog_agg_lock = asyncio.Lock()
_catalog_agg_prune_task: asyncio.Task | None = None
__all__ = ["Catalog", "catalog", "handle_catalog_response"]


async def _catalog_agg_prune_loop():
    # periodic cleanup of stale catalog aggregation entries to prevent memory growth
    import time as _time
    while True:
        await asyncio.sleep(60)
        try:
            async with _catalog_agg_lock:
                now = _time.time()
                expired = [k for k, v in list(_catalog_agg.items()) if now - v["ts"] > _catalog_agg_ttl_seconds]
                for k in expired:
                    _catalog_agg.pop(k, None)
                if expired:
                    logger.debug(f"Catalog aggregation prune: removed {len(expired)} stale entries, remaining={len(_catalog_agg)}")
        except Exception as e:
            logger.warning(f"Catalog aggregation prune error: {e}")


def start_catalog_agg_prune():
    global _catalog_agg_prune_task
    if _catalog_agg_prune_task is None or _catalog_agg_prune_task.done():
        _catalog_agg_prune_task = asyncio.create_task(_catalog_agg_prune_loop())


def _attach_trace_header(req: SipMessage) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id


from app.sip.sip_trace import sip_trace_log as _sip_trace_log


class Catalog:
    """GB28181 设备目录查询类。"""

    def __init__(self, sip_server):
        self.sip_server = sip_server

    async def send_catalog_query(self, asset, transport_info: tuple) -> str:
        """Send device catalog query (Catalog)."""
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        # Generate SN (Serial Number)
        sn = next_sn()  # P2-2: 统一 SN 生成策略

        # Build XML body for Catalog query
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_catalog@{sip_host_for_contact()}"
        req.headers["CSeq"] = "1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = xml_body

        # Send
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent CATALOG query to {device_id}, SN={sn}")
        _sip_trace_log(
            "catalog_query_sent",
            trace_id=trace_id,
            device_id=device_id,
            sn=sn,
            proto=proto,
            addr=str(addr),
        )

        return str(sn)

    async def send_device_info_query(self, asset, transport_info: tuple) -> str:
        """
        发送设备信息查询请求（DeviceInfo）

        Args:
            asset: 设备资产对象
            transport_info: (addr, proto, transport) 传输信息

        Returns:
            str: 请求SN
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        sn = next_sn()  # P2-2: 统一 SN 生成策略

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>DeviceInfo</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_deviceinfo@{sip_host_for_contact()}"
        req.headers["CSeq"] = "1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = xml_body

        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent DEVICEINFO query to {device_id}, SN={sn}")
        _sip_trace_log(
            "deviceinfo_query_sent",
            trace_id=trace_id,
            device_id=device_id,
            sn=sn,
            proto=proto,
            addr=str(addr),
        )

        return str(sn)

    async def send_device_status_query(self, asset, transport_info: tuple) -> str:
        """
        发送设备状态查询请求（DeviceStatus）

        Args:
            asset: 设备资产对象
            transport_info: (addr, proto, transport) 传输信息

        Returns:
            str: 请求SN
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        sn = next_sn()  # P2-2: 统一 SN 生成策略

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>DeviceStatus</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_devicestatus@{sip_host_for_contact()}"
        req.headers["CSeq"] = "1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = xml_body

        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent DEVICESTATUS query to {device_id}, SN={sn}")
        _sip_trace_log(
            "devicestatus_query_sent",
            trace_id=trace_id,
            device_id=device_id,
            sn=sn,
            proto=proto,
            addr=str(addr),
        )

        return str(sn)



async def handle_catalog_response(xml_body: str, device_id: str):
    """
    Parse Catalog XML and update Resources
    """
    root = parse_xml(xml_body)
    if root is None:
        await patch_device_catalog_runtime(
            device_id,
            {
                "catalog.last_response_at": utc_now_iso(),
                "catalog.last_error": "invalid_catalog_xml",
                "catalog.sync_state": "response_parse_failed",
            },
        )
        return

    sn = get_xml_text(root, "SN")
    sum_num_raw = get_xml_text(root, "SumNum", "")
    try:
        sum_num = int(str(sum_num_raw or "").strip() or "0")
    except Exception:
        sum_num = None  # SumNum解析异常时不应设为0（会导致多分片被丢弃），设为None
        logger.warning(f"Failed to parse SumNum '{sum_num_raw}' for device {device_id}, treating as unknown")

    device_list = find_child(root, "DeviceList")
    if device_list is None:
        await patch_device_catalog_runtime(
            device_id,
            {
                "catalog.last_response_at": utc_now_iso(),
                "catalog.last_item_count": 0,
                "catalog.last_error": "catalog_device_list_missing",
                "catalog.sync_state": "response_empty",
            },
        )
        return

    item_nodes = find_children(device_list, "Item")
    item_count = len(item_nodes)

    # 提取本次收到的项?dict
    items_data = []
    for item in item_nodes:
        channel_id = (get_xml_text(item, "DeviceID") or "").strip()  # None.strip()空指针异常防护
        ptz_type_str = get_xml_text(item, "PTZType")
        video_opt_mask_str = get_xml_text(item, "VideoOptMask")

        # 解析视频能力：VideoOptMask bit0 表示是否有视频
        # 0 = 无视频能力，> 0 = 有视频能力
        # W-18 VideoOptMask为空时has_video默认False，避免音频通道被误标为视频通道
        has_video: bool = False
        if video_opt_mask_str and video_opt_mask_str.isdigit():
            mask_val = int(video_opt_mask_str)
            has_video = mask_val > 0

        # 通道类型推断：PTZType > 0 ?摄像头；Parental > 0 ?目录
        ptz_type = int(ptz_type_str) if ptz_type_str and ptz_type_str.isdigit() else 0
        parental_str = get_xml_text(item, "Parental")
        parental = int(parental_str) if parental_str and parental_str.isdigit() else 0

        channel_type = 1  # 默认摄像头
        if parental > 0:
            channel_type = 0  # 目录/分组
        elif ptz_type == 0 and video_opt_mask_str == "0":
            channel_type = 3  # 音频通道（无云台也无视频）
        elif not has_video:
            channel_type = 3  # 无视频能力，音频

        items_data.append({
            "channel_id": channel_id,
            "name": (get_xml_text(item, "Name") or "").strip(),  # None.strip()空指针异常防护
            "status": (get_xml_text(item, "Status") or "").strip(),
            "parent_gb_id": (get_xml_text(item, "ParentID") or "").strip(),
            "civil_code": (get_xml_text(item, "CivilCode") or "").strip(),
            "parental": parental_str,
            "ptz_type": ptz_type_str,
            "channel_type": channel_type,
            "manufacturer": get_xml_text(item, "Manufacturer"),
            "model": get_xml_text(item, "Model"),
            "owner": get_xml_text(item, "Owner"),
            "address": get_xml_text(item, "Address"),
            "secrecy": get_xml_text(item, "Secrecy"),
            "longitude": get_xml_text(item, "Longitude"),
            "latitude": get_xml_text(item, "Latitude"),
            "has_video": has_video,
            "video_opt_mask": video_opt_mask_str,
        })

    received_total = item_count
    total_sum = sum_num
    # SumNum解析异常时total_sum为None，使用极大值确保收集所有分片
    _total_sum_effective = total_sum if total_sum is not None else 0x7FFFFFFF
    all_items = items_data

    # Redis 分片聚合逻辑
    if redis_client is not None and sn and _total_sum_effective > 0:  # 显式 None 守卫避免 pyright Never
        redis_key = f"pygbsentry:catalog:{device_id}:{sn}"

        # 将本次切片存入Redis List
        if items_data:
            # redis_client.rpush 接受多个值
            # 为了防止超过最大连接，可以打包为JSON
            json_items = [json.dumps(it, ensure_ascii=False) for it in items_data]
            # Redis 操作添加 try-except，避免 Redis 不可用时整个 catalog 同步失败
            try:
                # R24-06: 使用 pipeline 保证 RPUSH + EXPIRE 原子性
                pipe = redis_client.pipeline()
                pipe.rpush(redis_key, *json_items)
                pipe.expire(redis_key, 600)
                await pipe.execute()
            except Exception as e:
                logger.warning(f"Redis rpush/expire failed for catalog {device_id}: {e}")

        # R24-06: 使用 Lua 脚本原子化 LLEN + LRANGE + DELETE，消除 TOCTOU 竞态
        # 之前：LLEN → LRANGE → DELETE 三步非原子，并发分片可能导致双重处理或数据丢失
        # 现在：Lua 脚本在 Redis 服务端原子执行，返回 nil 表示未完成，返回 list 表示完成
        _CATALOG_AGG_LUA = """
        local n = redis.call('LLEN', KEYS[1])
        if n < tonumber(ARGV[1]) then
            return nil
        end
        local items = redis.call('LRANGE', KEYS[1], 0, -1)
        redis.call('DEL', KEYS[1])
        return items
        """
        try:
            lua_result = await redis_client.eval(
                _CATALOG_AGG_LUA, 1, redis_key, _total_sum_effective
            )
        except Exception as e:
            logger.warning(f"Redis Lua catalog agg failed for {device_id}: {e}")
            # R24-06: Redis 失败时设置为 error 状态，不再静默继续到 "synced"
            await patch_device_catalog_runtime(
                device_id,
                {
                    "catalog.last_response_at": utc_now_iso(),
                    "catalog.last_sn": str(sn or ""),
                    "catalog.last_error": f"redis_agg_failed: {e}",
                    "catalog.sync_state": "error",
                    "catalog.progress": 0,
                },
            )
            return

        if lua_result is None:
            # 尚未收集完毕 — 使用 LLEN 更新进度
            try:
                received_total = await redis_client.llen(redis_key)
            except Exception:
                received_total = len(all_items)
            await patch_device_catalog_runtime(
                device_id,
                {
                    "catalog.last_response_at": utc_now_iso(),
                    "catalog.last_sn": str(sn or ""),
                    "catalog.last_sum_num": int(_total_sum_effective),
                    "catalog.last_received_total": int(received_total),
                    "catalog.last_item_count": item_count,
                    "catalog.last_error": "",
                    "catalog.sync_state": "partial",
                    "catalog.progress": max(1, min(99, int(received_total * 100 / max(1, _total_sum_effective)))),
                },
            )
            logger.info(f"Catalog fragment aggregated for {device_id} SN={sn}, progress: {received_total}/{_total_sum_effective}")
            return

        # R24-06: Lua 脚本成功返回所有分片数据（list 类型）
        all_items = []
        for raw in lua_result:
            try:
                raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                all_items.append(json.loads(raw_str))
            except Exception as e:
                logger.warning(f"Failed to parse catalog item JSON: {e}")

        # received_total 用于后续 cleanup 判断
        received_total = len(all_items)

    # ?Redis 时的内存备用方案（分片聚合）
    elif sn and _total_sum_effective > 0:
        import time as _time
        key = (device_id, str(sn))
        async with _catalog_agg_lock:
            if key not in _catalog_agg:
                _catalog_agg[key] = {
                    "items": [],
                    "received": 0,
                    "total": _total_sum_effective,
                    "ts": _time.time(),
                }
            agg = _catalog_agg[key]
            agg["items"].extend(items_data)
            agg["received"] = len(agg["items"])
            received_total = agg["received"]

            # 清理过期条目（超?TTL 秒）
            expired = [k for k, v in list(_catalog_agg.items()) if _time.time() - v["ts"] > _catalog_agg_ttl_seconds]
            for k in expired:
                _catalog_agg.pop(k, None)

        if received_total < _total_sum_effective:
            await patch_device_catalog_runtime(
                device_id,
                {
                    "catalog.last_response_at": utc_now_iso(),
                    "catalog.last_sn": str(sn or ""),
                    "catalog.last_sum_num": int(_total_sum_effective),
                    "catalog.last_received_total": int(received_total),
                    "catalog.last_item_count": item_count,
                    "catalog.last_error": "",
                    "catalog.sync_state": "partial",
                    "catalog.progress": max(1, min(99, int(received_total * 100 / max(1, _total_sum_effective)))),
                },
            )
            logger.info(f"Catalog fragment (memory) for {device_id} SN={sn}, progress: {received_total}/{_total_sum_effective}")
            return

        # 收集完毕
        all_items = _catalog_agg.pop(key, {}).get("items", items_data)

    # ========== 开始入库逻辑 ==========
    async with AsyncSessionLocal() as session:
        stmt = select(Asset).where(Asset.gb_id == device_id)
        result = await session.execute(stmt)
        asset = result.scalars().first()

        if not asset:
            platform_stmt = select(ParentPlatform).where(
                (ParentPlatform.server_gb_id == device_id) | (ParentPlatform.client_gb_id == device_id)
            )
            platform_result = await session.execute(platform_stmt)
            platform = platform_result.scalars().first()
            if not platform:
                logger.warning(f"Received Catalog for unknown asset/platform: {device_id}")
                return
            asset = Asset(
                gb_id=device_id,
                name=f"Platform_{device_id}",
                tenant_id=platform.tenant_id or "default",
                decrypted_password=platform.decrypted_password or "",
                domain=settings.SIP_DOMAIN,
                transport=(platform.transport or "UDP"),
                ip_addr=platform.server_ip,
                port=platform.server_port,
                status=1,
            )
            session.add(asset)
            await session.flush()
            logger.info(f"Created platform asset for Catalog source: {device_id}, platform_id={platform.id}")

        allowed, limit, current = await check_channel_quota(session, asset.tenant_id or "default")
        remaining = None if limit <= 0 else max(limit - current, 0)

        seen_ids = set()

        # 批量预查
        channel_ids = [it.get("channel_id") for it in all_items if it.get("channel_id")]
        existing_resources = {}
        if channel_ids:
            stmt = select(Resource).where(
                Resource.gb_id.in_(channel_ids),
                Resource.tenant_id == (asset.tenant_id or "default")
            )
            res = await session.execute(stmt)
            for r in res.scalars().all():
                existing_resources[r.gb_id] = r

        for item in all_items:
            channel_id = item.get("channel_id")
            if not channel_id:
                continue

            seen_ids.add(channel_id)

            name = item.get("name")
            status = item.get("status")
            civil_code = item.get("civil_code")
            ptz_type_str = item.get("ptz_type")
            channel_type = item.get("channel_type", 1)
            address = item.get("address")
            longitude = item.get("longitude")
            latitude = item.get("latitude")
            has_video = item.get("has_video", False)  # R-06 与解析阶段默认值一致，VideoOptMask为空时默认无视频

            ptz_type = None
            if ptz_type_str and ptz_type_str.isdigit():
                ptz_type = int(ptz_type_str)
            is_online = 1 if status == "ON" else 0

            # 通道类型映射?=目录, 1=摄像? 2=报警, 3=音频
            if channel_type == 0:
                node_type = "directory"
            else:
                node_type = "channel"

            try:
                lon_f = float(longitude) if longitude else None
                lat_f = float(latitude) if latitude else None
            except ValueError:
                lon_f = None
                lat_f = None

            resource = existing_resources.get(channel_id)

            # 构建 capabilities 字段：包含 has_video、default_stream_type
            caps = {}  # caps={} was inside comment line
            existing_caps = {}
            if resource:
                existing_caps = resource.capabilities or {}

            if isinstance(existing_caps, dict):
                caps = dict(existing_caps)
            caps["has_video"] = bool(has_video)
            caps["catalog_has_video"] = bool(has_video)
            if channel_type:
                caps["catalog_channel_type"] = int(channel_type)

            if not resource:
                if remaining is not None and remaining <= 0:
                    continue
                effective_parent = item.get("parent_gb_id") or None
                resource = Resource(
                    tenant_id=asset.tenant_id or "default",
                    asset_id=asset.id,
                    gb_id=channel_id,
                    name=name,
                    status=is_online,
                    parent_gb_id=effective_parent,
                    civil_code=civil_code,
                    ptz_type=ptz_type if ptz_type is not None else 0,
                    node_type=node_type,
                    type=channel_type,
                    capabilities=caps,
                    address=address,
                    longitude=lon_f,
                    latitude=lat_f
                )
                session.add(resource)
                if remaining is not None:
                    remaining -= 1
            else:
                resource.asset_id = asset.id
                resource.name = name
                resource.status = is_online
                if civil_code:
                    resource.civil_code = civil_code
                if ptz_type is not None:
                    resource.ptz_type = ptz_type
                if resource.node_type != "directory" or node_type == "directory":
                    resource.node_type = node_type
                if channel_type:
                    resource.type = channel_type
                resource.capabilities = caps
                resource.address = address or resource.address
                if lon_f is not None:
                    resource.longitude = lon_f
                if lat_f is not None:
                    resource.latitude = lat_f

        # R24-06: 事务边界修复 — 将 upsert 和 cleanup 合并到单次 commit，
        # 保证 Resource 新增/更新与过期 Resource 删除是原子的，避免半同步状态
        # 触发清理条件：如果这是一次完整的同步 (总数明确且收集完毕，或者为单条响应)
        if (_total_sum_effective > 0 and received_total >= _total_sum_effective) or (_total_sum_effective <= 0) or (not sn):
            if seen_ids:
                logger.info(f"Triggering catalog cleanup for {device_id}, total_sum={_total_sum_effective}, seen_ids={len(seen_ids)}")
                existing_stmt = select(Resource.id, Resource.gb_id).where(Resource.asset_id == asset.id)
                if asset.tenant_id:
                    existing_stmt = existing_stmt.where(Resource.tenant_id == asset.tenant_id)
                existing_result = await session.execute(existing_stmt)
                ids_to_delete = [rid for rid, gid in existing_result.all() if gid not in seen_ids]
                _BATCH_SIZE = 500
                for batch_start in range(0, len(ids_to_delete), _BATCH_SIZE):
                    batch = ids_to_delete[batch_start:batch_start + _BATCH_SIZE]
                    await session.execute(delete(Resource).where(Resource.id.in_(batch)))
                logger.info(f"Cleaned up removed resources for device {device_id}, sync complete")

        await session.commit()

        await patch_device_catalog_runtime(
            device_id,
            {
                "catalog.last_response_at": utc_now_iso(),
                "catalog.last_sn": str(sn or ""),
                "catalog.last_sum_num": int(_total_sum_effective or 0),
                "catalog.last_received_total": int(received_total or 0),
                "catalog.last_item_count": item_count,
                "catalog.last_error": "",
                "catalog.sync_state": "synced",
                "catalog.progress": 100,
            },
        )
        logger.info(f"Updated Catalog for {device_id}, processed {len(all_items)} items total")
# Singleton instance
catalog = None
