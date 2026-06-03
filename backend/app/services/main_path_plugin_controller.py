from __future__ import annotations

import asyncio
import contextlib
from loguru import logger
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from app.services.plugin_runtime_config_helper import load_plugin_runtime_config
from app.models.stream_session import StreamSession
from app.services.plugin_stream_helper import (
    ensure_main_sub_stream_for_plugin,
    stop_stream_for_plugin,
)


StreamPolicy = Literal["auto", "main", "sub", "both"]
StreamType = Literal["main", "sub"]
StartMode = Literal["passive_only", "fallback_start"]




@dataclass(frozen=True)
class MainPathCtx:
    app_name: str
    stream_id: str
    ssrc: str
    channel_gb_id: str
    asset_gb_id: str | None
    stream_type: StreamType  # normalized main/sub
    tenant_id: str
    # 与 stream_sessions.media_server_id 对齐，便于插件将截图/API 定向到实际收流节点
    media_server_id: str | None = None


AnalysisHandler = Callable[[MainPathCtx, asyncio.Event], Awaitable[None]]


def _norm_stream_type(v: str | None) -> StreamType:
    s = (v or "").strip().lower()
    if s in {"0", "main"}:
        return "main"
    return "sub"


class MainPathPluginController:
    """
    主路分析控制器（给“码流/媒体联动型插件”复用）：
    - 被动：接收 `ON_ZLM_STREAM_REG`，根据 main/sub 触发分析
    - 主路优先：当 stream_policy="both" 时，main 到来抢占 sub（sub 只在 main 未激活时分析）
    - 取消/清理：unreg 到来会停止对应分析任务
    - 可选主动兜底：fallback_start 时在启动分析前调用
      `ensure_main_sub_stream_for_plugin(...)`，避免 DB/内存状态不一致导致漏分析
    - 可选主动停止：当 main 抢占 sub 时，可调用 stop_stream_for_plugin 释放 sub 资源
    """

    def __init__(
        self,
        *,
        plugin_id: str,
        enabled_default: bool = True,
        enabled_key: str = "enabled",
        debug_default: bool = False,
        stream_policy: StreamPolicy = "both",
        start_mode: StartMode = "fallback_start",
        dedup_by_ssrc: bool = True,
        stop_preempted_stream: bool = True,
        operator: str = "plugin",
        analysis_handler: AnalysisHandler,
    ) -> None:
        self.plugin_id = plugin_id
        self.enabled_default = bool(enabled_default)
        self.enabled_key = str(enabled_key or "enabled").strip() or "enabled"
        self.debug_default = bool(debug_default)
        self.stream_policy: StreamPolicy = stream_policy
        self.start_mode: StartMode = start_mode
        self.dedup_by_ssrc = dedup_by_ssrc
        self.stop_preempted_stream = stop_preempted_stream
        self.operator = operator
        self.analysis_handler = analysis_handler

        # ssrc -> stop_event/task
        self._tasks_by_ssrc: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}

        # channel_gb_id -> active route ("main"/"sub"/None)
        self._active_route_by_channel: dict[str, StreamType | None] = {}

        # channel_gb_id -> availability per route (track ssrc even if we decide not to analyze)
        self._availability: dict[str, dict[StreamType, dict[str, Any]]] = {}

        # channel-level lock to avoid race between main/sub events
        self._locks_by_channel: dict[str, asyncio.Lock] = {}

        # tenant cache for channel
        self._tenant_by_channel_cache: dict[str, str] = {}

    def _lock_for_channel(self, channel_gb_id: str) -> asyncio.Lock:
        lock = self._locks_by_channel.get(channel_gb_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks_by_channel[channel_gb_id] = lock
        return lock

    async def _resolve_tenant_id(self, db: AsyncSession, channel_gb_id: str) -> str:
        cached = self._tenant_by_channel_cache.get(channel_gb_id)
        if cached:
            return cached
        stmt = (
            select(Asset.tenant_id)
            .select_from(Resource)
            .join(Asset, Asset.id == Resource.asset_id)
            .where(Resource.gb_id == channel_gb_id)
        )
        tenant_id = (await db.execute(stmt)).scalars().first() or "default"
        tenant_id = str(tenant_id).strip() or "default"
        self._tenant_by_channel_cache[channel_gb_id] = tenant_id
        return tenant_id

    async def _load_runtime_config(self, db: AsyncSession, tenant_id: str) -> dict[str, Any]:
        # 复用统一 helper：负责从 SystemSetting 读取 plugin_runtime_config 并返回 dict
        return await load_plugin_runtime_config(
            db,
            plugin_id=self.plugin_id,
            tenant_id=tenant_id,
            base_config={},
        )

    def _fake_current_user(self, tenant_id: str) -> Any:
        # 只用于调用 plugin_stream_helper 的 safe_auth_audit；不需要真实用户对象。
        return type("PluginUser", (), {"tenant_id": tenant_id, "is_superuser": True, "username": "plugin"})()

    async def _stop_analysis_for_ssrc(self, *, ssrc: str, channel_gb_id: str, reason: str) -> None:
        item = self._tasks_by_ssrc.pop(ssrc, None)
        if not item:
            return
        task, evt = item
        evt.set()
        task.cancel()
        with contextlib.suppress(Exception):
            await task
        # If it was active route, clear active_route marker (conservative; next reg may reset)
        if self._active_route_by_channel.get(channel_gb_id) and self._active_route_by_channel.get(channel_gb_id) != None:
            # Don't aggressively clear; only clear when it matches availability ssrc
            pass

    async def _stop_stream_for_ssrc(self, db: AsyncSession, *, ssrc: str, tenant_id: str, reason: str) -> None:
        try:
            ss = (await db.execute(select(StreamSession).where(StreamSession.ssrc == str(ssrc)))).scalars().first()
        except Exception:
            logger.warning(f"查询流会话失败: ssrc={ssrc}")
            ss = None
        if not ss:
            return
        current_user = self._fake_current_user(tenant_id)
        await stop_stream_for_plugin(
            db=db,
            stream_session_id=str(ss.id),
            reason=reason,
            operator=self.operator,
            current_user=current_user,
        )

    async def _ensure_stream_if_needed(
        self,
        db: AsyncSession,
        *,
        channel_gb_id: str,
        stream_type: StreamType,
        ssrc: str,
        tenant_id: str,
        start_mode: StartMode,
    ) -> None:
        if start_mode != "fallback_start":
            return
        current_user = self._fake_current_user(tenant_id)
        await ensure_main_sub_stream_for_plugin(
            db=db,
            channel_gb_id=channel_gb_id,
            stream_type=stream_type,
            ssrc=ssrc,
            operator=self.operator,
            current_user=current_user,
        )

    def _should_start_analysis(
        self,
        *,
        stream_policy: StreamPolicy,
        channel_gb_id: str,
        stream_type: StreamType,
    ) -> bool:
        if stream_policy == "auto":
            return True
        if stream_policy == "main":
            return stream_type == "main"
        if stream_policy == "sub":
            return stream_type == "sub"
        # both
        active = self._active_route_by_channel.get(channel_gb_id)
        if stream_type == "main":
            return True
        # stream_type == "sub"
        return active != "main"

    async def handle_event(
        self,
        app_name: str,
        stream_id: str,
        ssrc: str,
        data: dict[str, Any] | None,
    ) -> None:
        data = data or {}
        ssrc = str(ssrc or "").strip()
        if not ssrc:
            return

        channel_gb_id = str(data.get("sentry_channel_id") or "").strip()
        if not channel_gb_id:
            return

        unreg = bool(data.get("sentry_stream_unreg"))
        stream_type = _norm_stream_type(str(data.get("sentry_stream_type") or "main"))
        asset_gb_id = str(data.get("sentry_asset_gb_id") or "").strip() or None

        async with self._lock_for_channel(channel_gb_id):
            # Ensure availability map exists
            if channel_gb_id not in self._availability:
                self._availability[channel_gb_id] = {"main": {}, "sub": {}}

            active_route_before = self._active_route_by_channel.get(channel_gb_id)

            # Update availability first
            if not unreg:
                self._availability[channel_gb_id][stream_type] = {"ssrc": ssrc, "asset_gb_id": asset_gb_id}
            else:
                cur = self._availability[channel_gb_id].get(stream_type) or {}
                if str(cur.get("ssrc") or "").strip() == ssrc:
                    self._availability[channel_gb_id][stream_type] = {}

            stop_analysis_ssrc: str | None = None
            preempt_stop_stream_ssrc: str | None = None
            start_route: StreamType | None = None
            start_ssrc: str | None = None
            start_asset_gb_id: str | None = None
            start_reason: str = "stream_reg"

            if unreg:
                # Stop analysis for this ssrc
                stop_analysis_ssrc = ssrc
                if active_route_before == stream_type:
                    self._active_route_by_channel[channel_gb_id] = None

                # both policy: main unreg => if sub is still available, start sub analysis
                if self.stream_policy == "both" and stream_type == "main":
                    sub_info = self._availability[channel_gb_id].get("sub") or {}
                    sub_ssrc = str(sub_info.get("ssrc") or "").strip()
                    if sub_ssrc:
                        start_route = "sub"
                        start_ssrc = sub_ssrc
                        start_asset_gb_id = sub_info.get("asset_gb_id")
                        start_reason = "main_unreg_start_sub"
            else:
                # reg event
                if self.stream_policy == "both":
                    if stream_type == "main":
                        # main always activates and preempts sub
                        start_route = "main"
                        start_ssrc = ssrc
                        start_asset_gb_id = asset_gb_id
                        self._active_route_by_channel[channel_gb_id] = "main"

                        # preempt sub (analysis + optionally stop stream)
                        sub_info = self._availability[channel_gb_id].get("sub") or {}
                        sub_ssrc = str(sub_info.get("ssrc") or "").strip()
                        if sub_ssrc and sub_ssrc != ssrc:
                            if active_route_before == "sub":
                                stop_analysis_ssrc = sub_ssrc
                            if self.stop_preempted_stream:
                                preempt_stop_stream_ssrc = sub_ssrc
                    else:
                        # sub reg: only start if main is NOT active
                        if active_route_before != "main":
                            start_route = "sub"
                            start_ssrc = ssrc
                            start_asset_gb_id = asset_gb_id
                            self._active_route_by_channel[channel_gb_id] = "sub"
                        else:
                            # main active => sub should not consume resources
                            if self.stop_preempted_stream:
                                preempt_stop_stream_ssrc = ssrc
                else:
                    if self._should_start_analysis(
                        stream_policy=self.stream_policy,
                        channel_gb_id=channel_gb_id,
                        stream_type=stream_type,
                    ):
                        start_route = stream_type
                        start_ssrc = ssrc
                        start_asset_gb_id = asset_gb_id
                        self._active_route_by_channel[channel_gb_id] = stream_type

            async with AsyncSessionLocal() as db:
                tenant_id = self._tenant_by_channel_cache.get(channel_gb_id)
                if not tenant_id:
                    tenant_id = await self._resolve_tenant_id(db, channel_gb_id)

                runtime_cfg = await self._load_runtime_config(db, tenant_id)

                enabled_val = runtime_cfg.get(self.enabled_key)
                enabled = bool(enabled_val) if enabled_val is not None else self.enabled_default
                debug_enabled = bool(runtime_cfg.get("debug", self.debug_default))
                if debug_enabled:
                    logger.info(
                        "[MainPathPluginController:%s] event app=%s stream_id=%s ssrc=%s unreg=%s channel=%s stream_type=%s enabled=%s effective_debug=1",
                        self.plugin_id,
                        app_name,
                        stream_id,
                        ssrc,
                        unreg,
                        channel_gb_id,
                        stream_type,
                        enabled,
                    )
                # 禁用时不再启动新分析，但仍要处理 unreg/停机清理
                if (not unreg) and (not enabled):
                    if debug_enabled:
                        logger.info(
                            "[MainPathPluginController:%s] disabled => skip start ssrc=%s channel=%s stream_type=%s",
                            self.plugin_id,
                            ssrc,
                            channel_gb_id,
                            stream_type,
                        )
                    # 运行时禁用：如果该 ssrc 已经启动过分析，则立刻停止，避免“禁用后仍后台跑”
                    if str(ssrc) in self._tasks_by_ssrc:
                        await self._stop_analysis_for_ssrc(
                            ssrc=str(ssrc),
                            channel_gb_id=channel_gb_id,
                            reason="plugin_disabled",
                        )
                        if debug_enabled:
                            logger.info(
                                "[MainPathPluginController:%s] disabled => stop existing task ssrc=%s channel=%s",
                                self.plugin_id,
                                ssrc,
                                channel_gb_id,
                            )
                    return

                def _as_stream_policy(v: Any, fallback: StreamPolicy) -> StreamPolicy:
                    s = str(v or "").strip().lower()
                    if s in {"auto", "main", "sub", "both"}:
                        return s  # type: ignore[return-value]
                    return fallback

                def _as_start_mode(v: Any, fallback: StartMode) -> StartMode:
                    s = str(v or "").strip().lower()
                    if s in {"passive_only", "fallback_start"}:
                        return s  # type: ignore[return-value]
                    return fallback

                effective_stream_policy: StreamPolicy = _as_stream_policy(runtime_cfg.get("stream_policy"), self.stream_policy)
                effective_start_mode: StartMode = _as_start_mode(runtime_cfg.get("start_mode"), self.start_mode)
                effective_dedup: bool = bool(runtime_cfg.get("dedup_by_ssrc", self.dedup_by_ssrc))
                effective_stop_preempted_stream: bool = bool(runtime_cfg.get("stop_preempted_stream", self.stop_preempted_stream))

                # runtime override：如果运行时配置与 controller 初始值不一致，需要重算路由与抢占决策。
                if effective_stream_policy != self.stream_policy or effective_stop_preempted_stream != self.stop_preempted_stream:
                    stop_analysis_ssrc = None
                    preempt_stop_stream_ssrc = None
                    start_route = None
                    start_ssrc = None
                    start_asset_gb_id = None

                    if unreg:
                        stop_analysis_ssrc = ssrc
                        if active_route_before == stream_type:
                            self._active_route_by_channel[channel_gb_id] = None

                        # main unreg 时：如果 sub 仍可用，自动切到 sub 分析
                        if effective_stream_policy == "both" and stream_type == "main":
                            sub_info = self._availability[channel_gb_id].get("sub") or {}
                            sub_ssrc = str(sub_info.get("ssrc") or "").strip()
                            if sub_ssrc:
                                start_route = "sub"
                                start_ssrc = sub_ssrc
                                start_asset_gb_id = sub_info.get("asset_gb_id")
                                self._active_route_by_channel[channel_gb_id] = "sub"
                    else:
                        if effective_stream_policy == "both":
                            if stream_type == "main":
                                start_route = "main"
                                start_ssrc = ssrc
                                start_asset_gb_id = asset_gb_id
                                self._active_route_by_channel[channel_gb_id] = "main"

                                # main 到来：抢占 sub（sub 只在 main 未激活时分析）
                                sub_info = self._availability[channel_gb_id].get("sub") or {}
                                sub_ssrc = str(sub_info.get("ssrc") or "").strip()
                                if sub_ssrc and sub_ssrc != ssrc:
                                    if active_route_before == "sub":
                                        stop_analysis_ssrc = sub_ssrc
                                    if effective_stop_preempted_stream and sub_ssrc in self._tasks_by_ssrc:
                                        preempt_stop_stream_ssrc = sub_ssrc
                            else:
                                # sub reg: 只有 main 未激活时才分析
                                if active_route_before != "main":
                                    start_route = "sub"
                                    start_ssrc = ssrc
                                    start_asset_gb_id = asset_gb_id
                                    self._active_route_by_channel[channel_gb_id] = "sub"
                                else:
                                    # main active => sub 不应占用资源（可选释放）
                                    if effective_stop_preempted_stream and ssrc in self._tasks_by_ssrc:
                                        preempt_stop_stream_ssrc = ssrc
                        else:
                            if self._should_start_analysis(
                                stream_policy=effective_stream_policy,
                                channel_gb_id=channel_gb_id,
                                stream_type=stream_type,
                            ):
                                start_route = stream_type
                                start_ssrc = ssrc
                                start_asset_gb_id = asset_gb_id
                                self._active_route_by_channel[channel_gb_id] = stream_type

                # reconcile actions with effective configs:
                # - stop_preempted_stream/stream_policy/start_mode/dedup 均在 runtime override 后被应用
                if stop_analysis_ssrc:
                    await self._stop_analysis_for_ssrc(
                        ssrc=str(stop_analysis_ssrc),
                        channel_gb_id=channel_gb_id,
                        reason="stream_unreg_or_preempt",
                    )
                    if debug_enabled:
                        logger.info(
                            "[MainPathPluginController:%s] stop analysis ssrc=%s channel=%s reason=%s",
                            self.plugin_id,
                            stop_analysis_ssrc,
                            channel_gb_id,
                            "stream_unreg_or_preempt",
                        )

                if preempt_stop_stream_ssrc and effective_stop_preempted_stream:
                    await self._stop_stream_for_ssrc(
                        db,
                        ssrc=str(preempt_stop_stream_ssrc),
                        tenant_id=tenant_id,
                        reason="main_priority_preempt",
                    )
                    if debug_enabled:
                        logger.info(
                            "[MainPathPluginController:%s] preempt stop stream ssrc=%s channel=%s",
                            self.plugin_id,
                            preempt_stop_stream_ssrc,
                            channel_gb_id,
                        )

                if start_route and start_ssrc:
                    if effective_dedup and str(start_ssrc) in self._tasks_by_ssrc:
                        return

                    if effective_start_mode == "fallback_start":
                        with contextlib.suppress(Exception):
                            await self._ensure_stream_if_needed(
                                db=db,
                                channel_gb_id=channel_gb_id,
                                stream_type=start_route,
                                ssrc=str(start_ssrc),
                                tenant_id=tenant_id,
                                start_mode=effective_start_mode,
                            )

                    media_server_id: str | None = None
                    try:
                        row = (
                            await db.execute(
                                select(StreamSession.media_server_id)
                                .where(StreamSession.ssrc == str(start_ssrc))
                                .order_by(StreamSession.start_time.desc())
                                .limit(1)
                            )
                        ).first()
                        if row and row[0]:
                            media_server_id = str(row[0]).strip() or None
                    except Exception:
                        logger.warning("查询媒体服务器ID失败")
                        media_server_id = None
                    stop_evt = asyncio.Event()
                    ctx = MainPathCtx(
                        app_name=app_name,
                        stream_id=stream_id,
                        ssrc=str(start_ssrc),
                        channel_gb_id=channel_gb_id,
                        asset_gb_id=start_asset_gb_id,
                        stream_type=start_route,
                        tenant_id=tenant_id,
                        media_server_id=media_server_id,
                    )

                    async def _runner() -> None:
                        await self.analysis_handler(ctx, stop_evt)

                    task = asyncio.create_task(_runner())
                    self._tasks_by_ssrc[str(start_ssrc)] = (task, stop_evt)
                    if debug_enabled:
                        logger.info(
                            "[MainPathPluginController:%s] start analysis route=%s ssrc=%s channel=%s stream_id=%s",
                            self.plugin_id,
                            start_route,
                            start_ssrc,
                            channel_gb_id,
                            stream_id,
                        )

    async def shutdown(self) -> None:
        """
        插件卸载/服务关闭时清理：取消所有分析任务。
        插件作者应在 register(pm) 中挂载到 HOOK_ON_SHUTDOWN。
        """
        tasks = list(self._tasks_by_ssrc.items())
        self._tasks_by_ssrc.clear()
        for _, (task, evt) in tasks:
            evt.set()
            task.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*(t for _, (t, _) in tasks), return_exceptions=True)

