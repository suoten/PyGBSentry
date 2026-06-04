"""
SNMP Trap 上报服务。
报警触发时，将告警内容转换为 SNMP Trap 数据报，发送到网管系统。
依赖 pysnmp（pip install pysnmp）。
"""
import asyncio
import datetime
import json
from loguru import logger
import os
import time

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.plugin_manager import HOOK_ON_ALARM
from app.db.session import AsyncSessionLocal
from app.models.system_setting import SystemSetting



PLUGIN_ID = "snmp_trap"
LOG_DIR = "logs/snmp_trap"

_DEFAULT_CONFIG = {
    "enabled": False,
    "trap_host": "127.0.0.1",
    "trap_port": 162,
    "community": "",
    "snmp_version": "2c",
    "oid_prefix": "1.3.6.1.4.1.99999",
    "include_alarms": True,
    "include_devices": True,
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl: float = 10.0


def _append_log(device_id: str, ok: bool, err: str | None = None) -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"snmp_trap_{today}.log")
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        if ok:
            line = f"[{ts}] device={device_id} ok=true\n"
        else:
            err_s = " ".join(str(err or "").split())[:300]
            line = f"[{ts}] device={device_id} ok=false err={err_s}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"SNMP Trap 日志写入失败: {e}")


async def _get_cfg() -> dict:
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl:
        return _cfg_cache
    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()
    any_enabled = False
    cfg = dict(_DEFAULT_CONFIG)
    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if isinstance(parsed, dict) and bool(parsed.get("enabled")):
                any_enabled = True
            for k in _DEFAULT_CONFIG:
                v = parsed.get(k)
                if v is not None and v != "":
                    cfg[k] = v
        except Exception:
            continue
    cfg["enabled"] = any_enabled or bool(cfg.get("enabled"))
    _cfg_cache = cfg
    _cfg_ts = now
    return cfg


def _build_trap_pdu(cfg: dict, alarm) -> list:
    """构造 SNMP Trap PDU (v2c)。"""
    device_id = str(getattr(alarm, "device_id", "") or "")
    alarm_type = str(getattr(alarm, "alarm_type", "") or "Alarm")
    priority = str(getattr(alarm, "priority", "4") or "4")
    description = str(getattr(alarm, "description", "") or "")
    t = getattr(alarm, "time", None)
    alarm_time = t.isoformat() if t and hasattr(t, "isoformat") else datetime.datetime.now(datetime.timezone.utc).isoformat()

    oid_base = str(cfg.get("oid_prefix") or _DEFAULT_CONFIG["oid_prefix"]).strip(".")
    enterprise_oid = f"{oid_base}.1"

    varbinds: list[tuple] = []
    # sysUpTime
    varbinds.append((f"{oid_base}.1.0", "Timeticks", int(time.time())))
    # snmpTrapOID
    varbinds.append((f"{oid_base}.2.0", "ObjectName", f"{oid_base}.0.1"))
    # alarmDeviceID
    varbinds.append((f"{oid_base}.3.0", "OctetString", device_id))
    # alarmType
    varbinds.append((f"{oid_base}.4.0", "OctetString", alarm_type))
    # alarmPriority
    varbinds.append((f"{oid_base}.5.0", "Integer32", int(priority) if priority.isdigit() else 4))
    # alarmDescription
    varbinds.append((f"{oid_base}.6.0", "OctetString", description))
    # alarmTime
    varbinds.append((f"{oid_base}.7.0", "OctetString", alarm_time))
    return varbinds


async def _send_trap(cfg: dict, alarm) -> bool:
    device_id = str(getattr(alarm, "device_id", "") or "").strip()
    trap_host = str(cfg.get("trap_host") or "127.0.0.1").strip()
    try:
        trap_port = int(cfg.get("trap_port") or 162)
    except Exception:
        trap_port = 162
    community = str(cfg.get("community") or "public")
    snmp_version = str(cfg.get("snmp_version") or "2c").strip()

    varbinds = _build_trap_pdu(cfg, alarm)

    try:
        from pysnmp.hlapi import (
            SnmpEngine, UdpTransportTarget, CommunityData, ContextData,
            sendNotification, notificationType, ObjectIdentity, ObjectType,
        )
        error_indication, error_status, error_index, var_bind_table = await asyncio.to_thread(
            _do_send_trap_sync,
            trap_host, trap_port, community, snmp_version, varbinds,
        )
        if error_indication:
            logger.warning("[SNMPTrap] Send failed: %s", error_indication)
            _append_log(device_id, ok=False, err=str(error_indication))
            return False
        _append_log(device_id, ok=True)
        logger.info(f"[SNMPTrap] Sent Trap for device={device_id} to {trap_host}:{trap_port}")
        return True
    except ImportError:
        logger.warning("[SNMPTrap] pysnmp not installed, skipping trap send")
        _append_log(device_id, ok=False, err="pysnmp_not_installed")
        return False
    except Exception as e:
        logger.error("[SNMPTrap] Error sending trap: %s", e)
        _append_log(device_id, ok=False, err=str(e))
        return False


def _do_send_trap_sync(trap_host, trap_port, community, snmp_version, varbinds):
    from pysnmp.hlapi import (
        SnmpEngine, UdpTransportTarget, CommunityData, ContextData,
        sendNotification, notificationType, ObjectIdentity, ObjectType,
    )
    if snmp_version == "3":
        auth = CommunityData(community, mpModel=3)
    else:
        auth = CommunityData(community, mpModel=1 if snmp_version == "1" else 0)
    transport = UdpTransportTarget((trap_host, trap_port), timeout=3, retries=1)
    iterator = sendNotification(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((trap_host, trap_port), timeout=3, retries=1),
        ContextData(),
        "trap",
        notificationType(
            *[
                ObjectType(ObjectIdentity(oid), val)
                for oid, typ, val in varbinds
            ]
        ),
    )
    error_indication, error_status, error_index, var_bind_table = next(iterator)
    return error_indication, error_status, error_index, var_bind_table


async def on_alarm(alarm) -> None:
    """报警 Hook：将告警以 SNMP Trap 发送。"""
    cfg = await _get_cfg()
    if not cfg.get("enabled"):
        return
    if not bool(cfg.get("include_alarms", True)):
        return
    await _send_trap(cfg, alarm)


_task: asyncio.Task | None = None


async def _run() -> None:
    """后台轮询：定时探测 snmp_trap_enabled 系统设置的变化（用于动态开关）。"""
    global _cfg_cache
    while True:
        try:
            cfg = await _get_cfg()
            if cfg.get("enabled"):
                pass  # 实际 Trap 发送由 hook 触发
        except Exception as e:
            logger.error(f"[SNMPTrap] Run error: {e}")
        await asyncio.sleep(60)


async def start() -> None:
    global _task
    logger.info("[SNMPTrap] Service started")
    _task = asyncio.create_task(_run())


async def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception) as e:
            logger.warning(f"SNMP Trap 任务取消超时: {e}")
        _task = None


def register(pm) -> None:
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
    logger.info("[SNMPTrap] Hook registered: HOOK_ON_ALARM")