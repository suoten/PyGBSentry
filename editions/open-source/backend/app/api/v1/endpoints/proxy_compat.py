from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.utils.stream_name import normalize_stream_name
from app.api.v1.endpoints.stream import list_streams
from app.api.v1.endpoints.integrations import (
    AccessSourcePayload,
    DesiredStatePayload,
    list_access_sources,
    create_access_source,
    update_access_source,
    delete_access_source,
    set_access_source_desired_state,
    list_ffmpeg_cmds,
)
from app.services.auth_audit import safe_auth_audit

router = APIRouter()

def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


async def _proxy_compat_audit(
    db: AsyncSession,
    user: User,
    *,
    action: str,
    result: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    await safe_auth_audit(
        db,
        module="integrations",
        action=action,
        source="proxy_compat",
        operator=user.username or "unknown",
        result=result,
        tenant_id=_audit_tid(user),
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


class ProxySavePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


def _pick(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _pick_bool(d: dict, *keys: str, default: bool | None = None) -> bool | None:
    for k in keys:
        if k not in d:
            continue
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in {"1", "true", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _guess_from_url(url: str) -> dict:
    u = (url or "").strip()
    if not u:
        return {"protocol": "RTSP", "host": "", "port": 554, "username": None, "password": None, "path": None, "extra": {}}
    p = urlparse(u)
    scheme = (p.scheme or "").lower()
    extra = {"source_url": u}
    if scheme in {"rtsp", "rtsps"}:
        host = p.hostname or ""
        port = int(p.port or 554)
        path = (p.path or "").lstrip("/")
        if p.query:
            path = f"{path}?{p.query}" if path else f"?{p.query}"
        return {
            "protocol": "RTSP",
            "host": host,
            "port": port,
            "username": p.username,
            "password": p.password,
            "path": path or None,
            "extra": extra,
        }
    if scheme in {"http", "https", "rtmp", "rtmps"}:
        extra["play_url"] = u
        return {"protocol": "SDK", "host": "sdk", "port": 0, "username": None, "password": None, "path": None, "extra": extra}
    extra["play_url"] = u
    return {"protocol": "SDK", "host": "sdk", "port": 0, "username": None, "password": None, "path": None, "extra": extra}


def _build_access_source_payload(raw: dict) -> AccessSourcePayload:
    src_url = _pick(raw, "srcUrl", "src_url", "src", "url", "source_url")
    guessed = _guess_from_url(src_url)
    name = _pick(raw, "name", "gbName", "gb_name") or (_pick(raw, "stream", "stream_name") or src_url or "proxy")
    stream = _pick(raw, "stream", "stream_name") or normalize_stream_name(name, fallback="proxy")
    enabled = _pick_bool(raw, "enable", "enabled", default=True)
    gb_id = _pick(raw, "gbId", "gb_id")
    gb_enabled = _pick_bool(raw, "gb_enabled", default=bool(gb_id))
    extra = {}
    if isinstance(raw.get("extra"), dict):
        extra.update(raw.get("extra") or {})
    extra.update(guessed.get("extra") or {})
    proxy_type = _pick(raw, "type")
    ffmpeg_cmd_key = _pick(raw, "ffmpegCmdKey", "ffmpeg_cmd_key")
    if proxy_type.lower() == "ffmpeg" and ffmpeg_cmd_key:
        extra["ffmpeg_cmd_key"] = ffmpeg_cmd_key
    if ffmpeg_cmd_key and "ffmpeg_cmd_key" not in extra:
        extra["ffmpeg_cmd_key"] = ffmpeg_cmd_key
    enable_audio = _pick_bool(raw, "enableAudio", "enable_audio", default=None)
    if enable_audio is not None:
        extra["proxy.enable_audio"] = bool(enable_audio)
    enable_mp4 = _pick_bool(raw, "enableMp4", "enable_mp4", default=None)
    if enable_mp4 is not None:
        extra["proxy.enable_mp4"] = bool(enable_mp4)
    timeout = _pick(raw, "timeout")
    if timeout:
        extra["proxy.timeout"] = timeout
    rtsp_type = _pick(raw, "rtspType", "rtsp_type")
    if rtsp_type:
        extra["proxy.rtsp_type"] = rtsp_type
    return AccessSourcePayload(
        name=name,
        protocol=_pick(raw, "protocol") or guessed["protocol"],
        host=_pick(raw, "host") or guessed["host"],
        port=int(raw.get("port") or guessed["port"] or 0),
        username=_pick(raw, "username") or guessed.get("username"),
        password=_pick(raw, "password") or guessed.get("password"),
        path=_pick(raw, "path") or guessed.get("path"),
        stream_name=stream,
        enabled=bool(enabled),
        gb_enabled=bool(gb_enabled),
        gb_id=gb_id or None,
        gb_name=_pick(raw, "gbName", "gb_name") or None,
        gb_parent_gb_id=_pick(raw, "gbParentGbId", "gb_parent_gb_id") or None,
        extra=extra,
    )


@router.get("/list")
async def proxy_list(
    query: str | None = None,
    pulling: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    rows = await list_access_sources(db=db, current_user=current_user)
    running_set: set[str] = set()
    if pulling is not None:
        try:
            streams = await list_streams(db=db, current_user=current_user)
            for s in streams or []:
                if s and s.get("app") == "live" and s.get("is_proxy") and s.get("stream"):
                    running_set.add(str(s.get("stream")))
        except Exception:
            running_set = set()
    q = (query or "").strip().lower()
    out = []
    for r in rows:
        protocol = str(r.get("protocol") or "").upper()
        if protocol not in {"RTSP", "ONVIF", "SDK", "RTMP"}:
            continue
        if q:
            hay = f"{r.get('name') or ''} {r.get('host') or ''} {r.get('path') or ''} {r.get('stream_name') or ''}".lower()
            if q not in hay:
                continue
        raw_stream = str(r.get("stream_name") or r.get("name") or r.get("id") or "")
        stream_name = normalize_stream_name(raw_stream, fallback=str(r.get("id") or ""))
        is_running = stream_name in running_set if running_set else (str((r.get("extra") or {}).get("runtime.proxy.is_running") or "").lower() == "true")
        if pulling is True and not is_running:
            continue
        if pulling is False and is_running:
            continue
        out.append(r)
    return out


@router.post("/save")
async def proxy_save(
    payload: ProxySavePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    raw = payload.model_dump()
    source_id = _pick(raw, "id")
    body = _build_access_source_payload(raw)
    if source_id and source_id not in {"0", "null", "none"}:
        await update_access_source(source_id=str(source_id), payload=body, db=db, current_user=current_user)
        return {"id": str(source_id)}
    created = await create_access_source(payload=body, db=db, current_user=current_user)
    return created


@router.post("/add")
async def proxy_add(
    payload: ProxySavePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    raw = payload.model_dump()
    raw.pop("id", None)
    body = _build_access_source_payload(raw)
    return await create_access_source(payload=body, db=db, current_user=current_user)


@router.post("/update")
async def proxy_update(
    payload: ProxySavePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    raw = payload.model_dump()
    source_id = _pick(raw, "id")
    if not source_id or source_id in {"0", "null", "none"}:
        await _proxy_compat_audit(
            db,
            current_user,
            action="proxy_update",
            result="failed",
            status_code=400,
            detail="Missing id",
            extra_summary="source_id=empty",
        )
        raise HTTPException(status_code=400, detail="Missing id")
    body = _build_access_source_payload(raw)
    await update_access_source(source_id=str(source_id), payload=body, db=db, current_user=current_user)
    return {"id": str(source_id)}


@router.post("/start")
@router.get("/start", include_in_schema=False)
async def proxy_start(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]),
)):
    return await set_access_source_desired_state(
        source_id=str(id),
        payload=DesiredStatePayload(state="running", enforce=True),
        db=db,
        current_user=current_user,
    )


@router.post("/stop")
@router.get("/stop", include_in_schema=False)
async def proxy_stop(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]),
)):
    return await set_access_source_desired_state(
        source_id=str(id),
        payload=DesiredStatePayload(state="stopped", enforce=True),
        db=db,
        current_user=current_user,
    )


@router.delete("/delete")
async def proxy_delete(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    return await delete_access_source(source_id=str(id), db=db, current_user=current_user)


@router.get("/ffmpeg_cmd/list")
async def proxy_ffmpeg_cmd_list(
    mediaServerId: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await list_ffmpeg_cmds(db=db, current_user=current_user)
