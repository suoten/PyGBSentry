"""ZLMediaKit 媒体节点管理器。

负责：
- 从 DB 加载 :class:`MediaNode` 行（内置 + 外置节点）。
- 通过 ZLM HTTP API（``/index/api/getServerConfig`` / ``getMediaList``）探活。
- 为 INVITE 流程选择最优节点（委托 ``app.core.media_nodes_db.select_best_db_node``）。
- 提供 RTP 端口开关 / 快照 / 录像等 ZLM API 的统一入口（委托
  ``app.services.zlm_rtp_server_service``）。

生命周期：
- ``start()`` 在应用 lifespan 启动时调用（``await media_manager.start()``），
  必须在无节点配置时也成功返回（仅记录 warning）。
- ``stop()`` 在 shutdown 时调用，best-effort 关闭资源。

模块级 ``media_manager`` 单例在导入时即创建（无副作用），lifespan 中调用其
``start()`` / ``stop()``。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.core.async_utils import fire_and_forget
from app.core.http_client import get_http_client
from app.db.session import AsyncSessionLocal
from app.models.media_node import MediaNode


class MediaManager:
    """管理 ZLMediaKit 媒体节点集群。"""

    def __init__(self) -> None:
        """Internal helper:   init  ."""
        self._started: bool = False
        self._embedded_failed: bool = False
        self._embedded_starting: bool = False
        # 节点探活缓存：node_id -> (is_online, last_seen_at, stream_count)
        self._node_health: dict[str, dict[str, Any]] = {}
        self._probe_lock = asyncio.Lock()
        self._probe_task: Optional[asyncio.Task] = None
        # 活跃流数（供 redis.py 注册节点负载时读取）
        self.active_stream_count: int = 0
        # 上一次全量探活时间
        self._last_probe_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动媒体节点管理：探活所有已配置节点。

        无节点配置时仅记录 warning 并返回（不抛异常），保证应用可继续启动。
        内置 ZLM 进程的实际拉起由外部脚本/容器编排负责，此处仅做健康探测。
        """
        if self._started:
            logger.debug("media_manager.start() called but already started")
            return
        self._embedded_failed = False
        logger.info("media_manager.start(): probing configured media nodes...")

        # 确保内置节点记录存在（便于运维展示）
        try:
            from app.core.media_nodes_db import ensure_embedded_media_node
            async with AsyncSessionLocal() as session:
                await ensure_embedded_media_node(session)
        except Exception as e:
            logger.warning(f"media_manager.start(): ensure_embedded_media_node failed: {e}")

        # 首次探活
        try:
            await self._probe_all_nodes()
        except Exception as e:
            logger.warning(f"media_manager.start(): initial probe failed: {e}")

        # 启动周期性探活后台任务
        if bool(getattr(settings, "MEDIA_NODES_ACTIVE_PROBE_ENABLED", True)):
            interval = int(getattr(settings, "MEDIA_NODES_ACTIVE_PROBE_INTERVAL_SECONDS", 30) or 30)
            try:
                self._probe_task = asyncio.create_task(self._probe_loop(interval))
                self._probe_task.add_done_callback(self._on_probe_task_done)
            except RuntimeError:
                logger.debug("media_manager.start(): no running loop for probe task")

        self._started = True
        online = sum(1 for v in self._node_health.values() if v.get("online"))
        if online == 0:
            logger.warning(
                "media_manager.start(): no media nodes online. "
                "If using embedded ZLM, ensure the MediaServer process is started "
                "(or set EMBEDDED_ZLM_ENABLED=false / ZLM_PREFER_EXTERNAL_NODES=true to skip)."
            )
        else:
            logger.info(f"media_manager.start(): {online} media node(s) online.")

    async def stop(self) -> None:
        """停止媒体节点管理：取消探活任务，best-effort 释放资源。"""
        if self._probe_task is not None and not self._probe_task.done():
            self._probe_task.cancel()
            try:
                await self._probe_task
            except (asyncio.CancelledError, Exception):
                logger.debug("task_cancelled")
            self._probe_task = None
        self._started = False
        logger.info("media_manager.stop(): media manager stopped.")

    def _on_probe_task_done(self, task: asyncio.Task) -> None:
        """Internal helper:  on probe task done."""
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.error(f"media_manager probe loop crashed: {exc!r}", exc_info=exc)

    # ------------------------------------------------------------------
    # P0-EventLoop: 端口检查与配置生成（异步，避免阻塞事件循环）
    # ------------------------------------------------------------------

    async def _ensure_port_free(self, port: int, host: str = "0.0.0.0") -> bool:
        """异步检查端口是否可用（不阻塞事件循环）。

        使用 asyncio.sleep 替代 time.sleep 进行重试等待，
        确保 SIP/媒体服务启动时不会阻塞 asyncio 事件循环。
        """
        import socket
        for _attempt in range(3):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, int(port)))
                sock.close()
                return True
            except OSError:
                # 端口被占用，等待后重试（使用 asyncio.sleep 不阻塞事件循环）
                await asyncio.sleep(0.5)
        return False

    async def _generate_config(self, node: Optional[dict] = None) -> dict:
        """异步生成媒体节点配置（调用 _ensure_port_free 检查端口）。

        将配置生成逻辑改为异步，确保端口检查不阻塞事件循环。
        """
        _config: dict[str, Any] = {}
        try:
            _rtp_port = int(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT", 30000) or 30000)
            # 异步检查 RTP 端口可用性
            _port_free = await self._ensure_port_free(_rtp_port)
            if not _port_free:
                logger.warning(f"RTP port {_rtp_port} is in use, ZLM will auto-assign")
            _config["rtp_proxy_port"] = _rtp_port
            _config["host"] = str(getattr(settings, "MEDIA_SERVER_HOST", "127.0.0.1") or "127.0.0.1")
            _config["http_port"] = int(getattr(settings, "MEDIA_SERVER_HTTP_PORT", 8880) or 8880)
            _config["secret"] = str(getattr(settings, "MEDIA_SERVER_SECRET", "") or "")
            if node:
                _config.update(node)
        except Exception as e:
            logger.warning(f"_generate_config failed: {e}")
        return _config

    # ------------------------------------------------------------------
    # 探活
    # ------------------------------------------------------------------

    async def _probe_loop(self, interval: int) -> None:
        """周期性探活所有节点的后台循环。"""
        while True:
            try:
                await asyncio.sleep(max(5, int(interval or 30)))
                await self._probe_all_nodes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"media_manager probe loop iteration failed: {e}")
                await asyncio.sleep(10)

    async def _probe_all_nodes(self) -> None:
        """并发探活所有 DB 媒体节点，更新 _node_health 缓存。"""
        async with self._probe_lock:
            self._last_probe_at = datetime.now(timezone.utc)
            try:
                from app.core.media_nodes_db import list_db_media_nodes
                async with AsyncSessionLocal() as session:
                    nodes = await list_db_media_nodes(session)
            except Exception as e:
                logger.warning(f"media_manager: list_db_media_nodes failed: {e}")
                return
            if not nodes:
                self.active_stream_count = 0
                return
            results = await asyncio.gather(
                *[self._probe_one(n) for n in nodes], return_exceptions=True
            )
            total_streams = 0
            online = 0
            for n, res in zip(nodes, results):
                if isinstance(res, Exception):
                    self._node_health[n.id] = {
                        "online": False,
                        "last_seen_at": None,
                        "stream_count": 0,
                        "error": str(res),
                    }
                    # 回写 DB is_online=False（best-effort）
                    fire_and_forget(self._update_node_online_status(n.id, False, str(res)))
                    continue
                is_online, stream_count = res
                self._node_health[n.id] = {
                    "online": is_online,
                    "last_seen_at": datetime.now(timezone.utc).isoformat() if is_online else None,
                    "stream_count": stream_count,
                    "error": "" if is_online else "probe failed",
                }
                if is_online:
                    online += 1
                    total_streams += int(stream_count or 0)
                fire_and_forget(self._update_node_online_status(n.id, is_online, ""))
            self.active_stream_count = total_streams
            logger.debug(f"media_manager probe: {online}/{len(nodes)} online, {total_streams} streams")

    async def _probe_one(self, node) -> tuple[bool, int]:
        """探活单个节点：调用 getServerConfig 验证存活，getMediaList 获取流数。"""
        host = str(getattr(node, "host", "") or "")
        http_port = int(getattr(node, "http_port", 0) or 0)
        secret = str(getattr(node, "secret", "") or "")
        if not host or http_port <= 0:
            return False, 0
        url = f"http://{host}:{http_port}/index/api/getServerConfig"
        try:
            client = await get_http_client()
            r = await client.post(url, data={"secret": secret}, timeout=3.0)
            if r.status_code >= 400:
                return False, 0
            data = r.json()
            if data.get("code") not in (0, "0"):
                return False, 0
        except Exception as e:
            logger.warning(f"media_manager probe getServerConfig failed for {host}:{http_port}: {e}")
            return False, 0
        # 获取流数
        stream_count = 0
        try:
            list_url = f"http://{host}:{http_port}/index/api/getMediaList"
            r2 = await client.post(list_url, data={"secret": secret}, timeout=2.0)
            if r2.status_code < 400:
                d2 = r2.json()
                if d2.get("code") in (0, "0"):
                    media_list = d2.get("data")
                    stream_count = len(media_list) if isinstance(media_list, list) else 0
        except Exception as e:
            logger.warning(f"media_manager probe getMediaList failed for {host}:{http_port}: {e}")
        return True, int(stream_count or 0)

    async def _update_node_online_status(self, node_id: str, is_online: bool, error: str) -> None:
        """best-effort 回写节点的 is_online / last_seen_at / last_probe_error。"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(MediaNode).where(MediaNode.id == node_id))
                node = result.scalars().first()
                if node is None:
                    return
                node.is_online = bool(is_online)
                if is_online:
                    node.last_seen_at = datetime.now(timezone.utc)
                    node.last_probe_error = None
                else:
                    node.last_probe_error = (error or "probe failed")[:500]
                await session.commit()
        except Exception as e:
            logger.warning(f"media_manager: update node {node_id} online status failed: {e}")

    async def probe_node(self, node_id: str) -> dict[str, Any]:
        """手动探活指定节点，返回健康信息 dict。"""
        try:
            from app.core.media_nodes_db import get_db_media_node_by_id
            async with AsyncSessionLocal() as session:
                node = await get_db_media_node_by_id(session, node_id)
        except Exception as e:
            logger.warning(f"media_manager.probe_node: get node {node_id} failed: {e}")
            return {"online": False, "error": str(e)}
        if node is None:
            return {"online": False, "error": "node not found"}
        is_online, stream_count = await self._probe_one(node)
        self._node_health[node_id] = {
            "online": is_online,
            "last_seen_at": datetime.now(timezone.utc).isoformat() if is_online else None,
            "stream_count": stream_count,
            "error": "" if is_online else "probe failed",
        }
        fire_and_forget(self._update_node_online_status(node_id, is_online, ""))
        return self._node_health[node_id]

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    async def is_running(self) -> bool:
        """是否有至少一个媒体节点在线。"""
        if not self._node_health:
            # 缓存为空时做一次轻量探活
            try:
                await self._probe_all_nodes()
            except Exception as e:
                logger.warning(f"media_manager.is_running probe failed: {e}")
        return any(v.get("online") for v in self._node_health.values())

    def embedded_deploy_known_failed(self) -> bool:
        """内置 ZLM 部署是否已知永久失败（避免反复重试拉起）。"""
        return bool(self._embedded_failed)

    def mark_embedded_failed(self, reason: str = "") -> None:
        """标记内置 ZLM 部署失败（health_service / startup 检测到致命错误时调用）。"""
        self._embedded_failed = True
        if reason:
            logger.warning(f"media_manager: embedded ZLM deploy marked failed: {reason}")

    async def _detect_external_media_nodes_configured(self) -> dict[str, Any]:
        """检测是否配置了外置媒体节点（DB 非内置节点或 MEDIA_NODES 环境变量）。

        供 health_service 决定是否跳过内置 ZLM 拉起。
        返回 ``{"has_external": bool, "db_external_count": int, "env_count": int}``。
        """
        db_external = 0
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(MediaNode).where(
                        (MediaNode.is_embedded.is_(False)) | (MediaNode.is_embedded.is_(None))
                    )
                )
                rows = result.scalars().all()
                db_external = len(rows)
        except Exception as e:
            logger.warning(f"media_manager._detect_external: query DB failed: {e}")

        env_count = 0
        raw = getattr(settings, "MEDIA_NODES", None)
        if raw and str(raw).strip():
            import json
            try:
                nodes = json.loads(raw)
                if isinstance(nodes, list):
                    env_count = len(nodes)
            except Exception:
                env_count = 1  # 配置存在但解析失败，保守视为 1

        return {
            "has_external": db_external > 0 or env_count > 0,
            "db_external_count": db_external,
            "env_count": env_count,
        }

    # ------------------------------------------------------------------
    # 节点选择与增删
    # ------------------------------------------------------------------

    async def select_media_node(
        self, exclude_node_ids: Optional[list[str]] = None
    ) -> Optional[Any]:
        """选择最优媒体节点（委托 select_best_db_node，Least Connections）。"""
        try:
            from app.core.media_nodes_db import select_best_db_node
            async with AsyncSessionLocal() as session:
                return await select_best_db_node(session, exclude_node_ids=exclude_node_ids)
        except Exception as e:
            logger.error(f"media_manager.select_media_node failed: {e}")
            return None

    async def get_media_server(self) -> Optional[Any]:
        """获取一个可用媒体节点（select_media_node 的别名）。"""
        return await self.select_media_node()

    async def get_media_server_by_id(self, node_id: str) -> Optional[Any]:
        """按 ID 获取媒体节点（RuntimeMediaNode）。"""
        if not node_id:
            return None
        try:
            from app.core.media_nodes_db import get_db_media_node_by_id
            async with AsyncSessionLocal() as session:
                return await get_db_media_node_by_id(session, node_id)
        except Exception as e:
            logger.warning(f"media_manager.get_media_server_by_id({node_id}) failed: {e}")
            return None

    async def get_all_media_nodes(self) -> list[Any]:
        """获取所有 DB 媒体节点（RuntimeMediaNode 列表）。"""
        try:
            from app.core.media_nodes_db import list_db_media_nodes
            async with AsyncSessionLocal() as session:
                return await list_db_media_nodes(session)
        except Exception as e:
            logger.warning(f"media_manager.get_all_media_nodes failed: {e}")
            return []

    async def add_media_node(self, node: MediaNode) -> bool:
        """新增媒体节点到 DB。"""
        try:
            async with AsyncSessionLocal() as session:
                session.add(node)
                await session.commit()
                await session.refresh(node)
            fire_and_forget(self.probe_node(node.id))
            logger.info(f"media_manager: added media node {node.id} ({node.ip}:{node.http_port})")
            return True
        except Exception as e:
            logger.error(f"media_manager.add_media_node failed: {e}")
            return False

    async def remove_media_node(self, node_id: str) -> bool:
        """从 DB 删除媒体节点。"""
        if not node_id:
            return False
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(MediaNode).where(MediaNode.id == node_id))
                node = result.scalars().first()
                if node is None:
                    return False
                await session.delete(node)
                await session.commit()
            self._node_health.pop(node_id, None)
            logger.info(f"media_manager: removed media node {node_id}")
            return True
        except Exception as e:
            logger.error(f"media_manager.remove_media_node({node_id}) failed: {e}")
            return False

    # ------------------------------------------------------------------
    # ZLM API 代理（委托 zlm_rtp_server_service）
    # ------------------------------------------------------------------

    async def open_rtp_server(self, node_id: str, **kwargs: Any) -> dict[str, Any]:
        """在指定节点上打开 RTP 收流端口（委托 zlm_rtp_server_service.open_rtp_server）。"""
        from app.services.zlm_rtp_server_service import open_rtp_server
        node = await self.get_media_server_by_id(node_id)
        if node is None:
            raise ValueError(f"media node {node_id} not found")
        return await open_rtp_server(
            host=str(node.host),
            http_port=int(node.http_port or 0),
            secret=str(node.secret or ""),
            **kwargs,
        )

    async def close_rtp_server(self, node_id: str, stream_id: str) -> dict[str, Any]:
        """在指定节点上关闭 RTP 收流端口。"""
        from app.services.zlm_rtp_server_service import close_rtp_server
        node = await self.get_media_server_by_id(node_id)
        if node is None:
            raise ValueError(f"media node {node_id} not found")
        return await close_rtp_server(
            host=str(node.host),
            http_port=int(node.http_port or 0),
            secret=str(node.secret or ""),
            stream_id=str(stream_id or ""),
        )

    # ------------------------------------------------------------------
    # Webhook URL resolution & Docker detection
    # ------------------------------------------------------------------

    def _is_loopback_host(self, host: str) -> bool:
        """Check if the given host is a loopback address."""
        if not host:
            return True
        h = str(host).strip().lower()
        return h in ("localhost", "127.0.0.1", "::1", "0.0.0.0")

    def _is_running_in_docker(self) -> bool:
        """Detect if the process is running inside a Docker container."""
        import os
        if os.environ.get("RUNNING_IN_DOCKER", "").lower() in ("true", "1", "yes"):
            return True
        # Check for .dockerenv file
        return os.path.exists("/.dockerenv")

    def _detect_docker_gateway_ip(self) -> Optional[str]:
        """Detect the Docker host gateway IP (for bare-metal backend reachable from container).

        Returns the gateway IP string or None if not in Docker / detection fails.
        """
        if not self._is_running_in_docker():
            return None
        import subprocess
        try:
            result = subprocess.run(
                ["sh", "-c", "ip route | awk '/default/ {print $3; exit}'"],
                capture_output=True, text=True, timeout=3,
            )
            gw = result.stdout.strip()
            if gw and self._is_loopback_host(gw) is False:
                return gw
        except Exception as e:
            logger.debug(f"media_manager: failed to detect default gateway: {e}")
        return None

    def _resolve_webhook_base(self, webhook_url: Optional[str]) -> str:
        """Resolve the ZLM webhook base URL.

        Priority:
        1. Explicit ``webhook_url`` argument
        2. ``MEDIA_SERVER_HOOK_BASE_URL`` setting
        3. ``BACKEND_PUBLIC_HOST`` + ``BACKEND_PUBLIC_PORT``
        4. Docker gateway IP (if in Docker)
        5. Fallback to localhost
        """
        # 1. Explicit argument
        if webhook_url:
            return webhook_url.rstrip("/")
        # 2. Setting
        setting_url = str(getattr(settings, "MEDIA_SERVER_HOOK_BASE_URL", "") or "")
        if setting_url:
            return setting_url.rstrip("/")
        # 3. Backend public host + port
        host = str(getattr(settings, "BACKEND_PUBLIC_HOST", "localhost") or "localhost")
        port = int(getattr(settings, "BACKEND_PUBLIC_PORT", 8000) or 8000)
        # 4. Docker gateway detection
        if self._is_loopback_host(host) and self._is_running_in_docker():
            gw = self._detect_docker_gateway_ip()
            if gw:
                host = gw
        # 5. Build URL
        return f"http://{host}:{port}/index/hook"


# 模块级单例：导入即创建（无副作用），lifespan 中调用 start()/stop()
media_manager = MediaManager()
