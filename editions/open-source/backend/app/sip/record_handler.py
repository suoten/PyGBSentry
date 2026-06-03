import json
import time
from loguru import logger  # FIXED: 统一使用 loguru 替代 logging
from app.core.redis import redis_client
from app.core.xml_utils import parse_xml, get_xml_text, find_child, find_children


# In-memory fallback cache for RecordInfo query results.
# Key: SN (string). Value: list[dict] (records).
# Used by API polling in `app/api/v1/endpoints/device_record.py`.
record_query_cache: dict[str, list[dict]] = {}
record_query_meta_cache: dict[str, dict] = {}
_record_agg: dict[tuple[str, str], dict] = {}
_record_agg_ttl_seconds = 600
_record_cache_ttl_seconds = 600
_record_cache_max_size = 5000


def _cleanup_record_caches() -> None:
    now = time.time()
    stale = [k for k, v in record_query_meta_cache.items() if now - v.get("_ts", 0) > _record_cache_ttl_seconds]
    for k in stale:
        record_query_cache.pop(k, None)
        record_query_meta_cache.pop(k, None)
    if len(record_query_meta_cache) > _record_cache_max_size:
        oldest = sorted(record_query_meta_cache.items(), key=lambda x: x[1].get("_ts", 0))
        for k, _ in oldest[:len(oldest) - _record_cache_max_size // 2]:
            record_query_cache.pop(k, None)
            record_query_meta_cache.pop(k, None)

async def handle_record_info_response(xml_body: str, device_id: str):
    """
    Parse RecordInfo Response
    """
    root = parse_xml(xml_body)
    if root is None:
        return

    sn = get_xml_text(root, "SN")

    if sn and sn.isdigit():
        try:
            import app.services.platform_service as _ps_mod
            svc = getattr(_ps_mod, "platform_service", None)
            if svc and int(sn) in svc._cascade_record_queries:
                await svc.forward_cascade_record_response(int(sn), xml_body)
                return
        except Exception as e:
            logger.warning(f"Cascade record forward failed for SN={sn}: {e}")
    
    record_list = find_child(root, "RecordList")
    if record_list is None:
        return
    sum_num_raw = get_xml_text(record_list, "SumNum", "") or get_xml_text(root, "SumNum", "")
    try:
        sum_num = int(str(sum_num_raw or "0").strip() or "0")
    except Exception:
        sum_num = 0
    now = time.time()
    for k in list(_record_agg.keys()):
        st = _record_agg.get(k) or {}
        if (now - float(st.get("last_at") or 0.0)) > _record_agg_ttl_seconds:
            _record_agg.pop(k, None)

    def _record_key(r: dict) -> str:
        return "|".join(
            [
                str(r.get("device_id") or ""),
                str(r.get("start_time") or ""),
                str(r.get("end_time") or ""),
                str(r.get("file_path") or ""),
                str(r.get("name") or ""),
            ]
        )

    records: list[dict] = []
    for item in find_children(record_list, "Item"):
        record = {
            "device_id": get_xml_text(item, "DeviceID"),
            "name": get_xml_text(item, "Name"),
            "start_time": get_xml_text(item, "StartTime"),
            "end_time": get_xml_text(item, "EndTime"),
            "file_path": get_xml_text(item, "FilePath"),
            "file_size": get_xml_text(item, "FileSize", "0"),
            "type": "device",
        }
        records.append(record)

    if sn:
        agg_key = (str(device_id or ""), str(sn))
        st = _record_agg.get(agg_key) or {"seen": set(), "records": [], "sum_num": 0, "last_at": now}
        st["last_at"] = now
        try:
            st["sum_num"] = max(int(st.get("sum_num") or 0), int(sum_num or 0))
        except Exception:
            st["sum_num"] = int(sum_num or 0)

        seen: set = st.get("seen") if isinstance(st.get("seen"), set) else set()  # FIXED: None guard for set assignment
        merged: list = st.get("records") if isinstance(st.get("records"), list) else []  # FIXED: None guard for list assignment
        for r in records:
            key = _record_key(r)
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
            
        # VOD Record Gap Detection: Sort and stitch timelines
        try:
            from datetime import datetime
            
            def parse_dt(s: str):
                try:
                    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
                except Exception:
                    return None

            # Sort by start_time
            merged.sort(key=lambda x: parse_dt(str(x.get("start_time") or "")) or datetime.min)
            
            # Detect gaps > 5 seconds
            for i in range(1, len(merged)):
                prev = merged[i-1]
                curr = merged[i]
                prev_end = parse_dt(str(prev.get("end_time") or ""))
                curr_start = parse_dt(str(curr.get("start_time") or ""))
                if prev_end and curr_start:
                    diff = (curr_start - prev_end).total_seconds()
                    if diff > 5:
                        curr["_gap_before_seconds"] = diff
        except Exception as e:
            logger.warning(f"Failed to detect record gaps: {e}")
            
        st["seen"] = seen
        st["records"] = merged
        _record_agg[agg_key] = st
        records = merged
        _cleanup_record_caches()
        record_query_meta_cache[str(sn)] = {
            "sn": str(sn),
            "device_id": str(device_id or ""),
            "sum_num": int(st.get("sum_num") or 0),
            "received": int(len(records)),
            "_ts": time.time(),
        }

    # Always store an in-memory copy for API polling fallback.
    # This complements Redis storage (if enabled).
    if sn:
        try:
            record_query_cache[str(sn)] = records
        except Exception as e:
            logger.error(f"Failed to store records in memory cache: {e}")
        
    if records and redis_client is not None:  # FIXED: 显式 None 守卫避免 pyright Never
        # Key: gb:records:{sn}
        # Value: List of JSON strings
        key = f"gb:records:{sn}"
        try:
            # Store in Redis with 10-minute expiration
            existing = await redis_client.get(key)
            if existing:
                try:
                    all_records = json.loads(existing)
                    if not isinstance(all_records, list):
                        all_records = []
                except Exception:
                    all_records = []
            else:
                all_records = []

            existing_seen = set()
            for r in all_records:
                if isinstance(r, dict):
                    existing_seen.add(_record_key(r))
            for r in records:
                if _record_key(r) in existing_seen:
                    continue
                all_records.append(r)
                existing_seen.add(_record_key(r))
                
            _RECORD_CACHE_TTL_SECONDS = 600  # FIXED: 魔法数字→常量（录像查询缓存TTL）
            await redis_client.setex(key, _RECORD_CACHE_TTL_SECONDS, json.dumps(all_records))
            meta_key = f"gb:records_meta:{sn}"
            try:
                meta = {
                    "sn": str(sn),
                    "device_id": str(device_id or ""),
                    "sum_num": int((record_query_meta_cache.get(str(sn)) or {}).get("sum_num") or sum_num or 0),
                    "received": int(len(all_records)),
                }
                await redis_client.setex(meta_key, _RECORD_CACHE_TTL_SECONDS, json.dumps(meta))  # FIXED: 魔法数字→复用常量
            except Exception as e:
                logger.warning(f"Error: {e}")
            logger.info(f"Stored {len(records)} records in Redis for SN {sn}")
        except Exception as e:
            logger.error(f"Failed to store records in Redis: {e}")
    else:
        logger.warning("No records to store or Redis not available")