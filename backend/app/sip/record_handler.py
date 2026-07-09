"""GB28181 RecordInfo 响应解析与缓存。

本模块负责解析设备返回的 ``CmdType=RecordInfo`` XML 响应，将其中每个
``<Item>`` 转换为标准化的录像条目字典，并按 SN 缓存最近一次查询结果，
供 ``device_record`` REST 端点轮询读取。

缓存使用带容量上限的字典（FIFO 淘汰），避免长时间运行后内存无限增长。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from loguru import logger

from app.core.xml_utils import parse_xml, get_xml_text

# 缓存上限：保留最近 N 次 RecordInfo 查询的结果
_RECORD_QUERY_CACHE_MAX = 200


def _evict_if_full(cache: "OrderedDict[str, Any]", max_size: int) -> None:
    """FIFO 淘汰最早的条目，保证缓存大小不超过 max_size。"""
    while len(cache) > max_size:
        try:
            cache.popitem(last=False)
        except KeyError:
            break


# SN -> list[dict]：录像条目列表（每项含 DeviceID/Name/FilePath/StartTime/EndTime 等）
record_query_cache: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()

# SN -> dict：录像查询元信息（含 sum_num/received/device_id 等）
record_query_meta_cache: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def _parse_record_items(root) -> list[dict[str, Any]]:
    """从 RecordInfo 响应根节点提取所有 <Item>，返回标准化的录像条目列表。"""
    items: list[dict[str, Any]] = []
    if root is None:
        return items
    # Item 可直接位于根下，也可能位于 <ItemList> 内；两种布局都兼容
    item_elems = root.findall(".//Item")
    for item in item_elems:
        try:
            entry: dict[str, Any] = {
                "device_id": get_xml_text(item, "DeviceID") or "",
                "name": get_xml_text(item, "Name") or "",
                "file_path": get_xml_text(item, "FilePath") or "",
                "address": get_xml_text(item, "Address") or "",
                "start_time": get_xml_text(item, "StartTime") or "",
                "end_time": get_xml_text(item, "EndTime") or "",
                "secrecy": get_xml_text(item, "Secrecy") or "0",
                "type": get_xml_text(item, "Type") or "time",
            }
            items.append(entry)
        except Exception as e:
            logger.warning(f"Failed to parse RecordInfo Item: {e}")
            continue
    return items


async def handle_record_info_response(body: str, gb_id: str) -> None:
    """解析 RecordInfo 响应并写入缓存。

    被_handlers.py 在收到 ``CmdType=RecordInfo`` 的 MESSAGE 时以 fire-and-forget
    方式调用。SN 作为缓存键，供 ``device_record`` 端点按 SN 轮询读取结果。

    解析失败时记录警告但不抛异常，避免拖垮 fire-and-forget 任务。
    """
    if not body:
        logger.warning(f"Empty RecordInfo body from {gb_id}")
        return
    try:
        root = parse_xml(body)
    except Exception as e:
        logger.warning(f"Failed to parse RecordInfo XML from {gb_id}: {e}")
        return
    if root is None:
        logger.warning(f"RecordInfo XML root is None from {gb_id}")
        return

    sn = get_xml_text(root, "SN") or ""
    sum_num_raw = get_xml_text(root, "SumNum") or "0"
    device_id_xml = get_xml_text(root, "DeviceID") or gb_id
    name = get_xml_text(root, "Name") or ""

    try:
        sum_num = int(sum_num_raw)
    except (TypeError, ValueError):
        sum_num = 0

    items = _parse_record_items(root)

    sn_key = str(sn) if sn else ""
    if not sn_key:
        # 没有 SN 时无法被端点轮询，仅记录日志
        logger.warning(f"RecordInfo from {gb_id} missing SN, cannot cache result")
        return

    _evict_if_full(record_query_cache, _RECORD_QUERY_CACHE_MAX)
    record_query_cache[sn_key] = items

    _evict_if_full(record_query_meta_cache, _RECORD_QUERY_CACHE_MAX)
    record_query_meta_cache[sn_key] = {
        "sn": sn_key,
        "sum_num": sum_num,
        "received": len(items),
        "device_id": device_id_xml,
        "name": name,
        "from_gb_id": gb_id,
    }

    logger.info(
        f"RecordInfo cached: gb_id={gb_id} sn={sn_key} sum_num={sum_num} received={len(items)}"
    )


# FIX: [2026-07-03] server.py 的 prune loop 导入此函数但该函数不存在，导致每 5 秒报错 [全栈工程师]
def periodic_cleanup_record_caches() -> None:
    """定期清理录像查询缓存，防止长时间运行后内存无限增长。

    被 ``server.py`` 的 ``_prune_loop`` 每 5 秒调用一次。
    对 ``record_query_cache`` 和 ``record_query_meta_cache`` 执行 FIFO 淘汰。
    """
    _evict_if_full(record_query_cache, _RECORD_QUERY_CACHE_MAX)
    _evict_if_full(record_query_meta_cache, _RECORD_QUERY_CACHE_MAX)
