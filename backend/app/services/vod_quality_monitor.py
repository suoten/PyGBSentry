"""
点播质量监控与自适应服务 - Vod Quality Monitor Service

功能：
1. 播放质量实时监控
2. 智能源选择与故障转移
3. 自适应缓冲控制
4. 画质自动降级/升级
5. 性能指标收集与上报
"""

import asyncio
from loguru import logger
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable, Awaitable




class QualityLevel(Enum):
    """画质等级"""
    EXCELLENT = "excellent"  # 极好
    GOOD = "good"           # 良好
    FAIR = "fair"           # 一般
    POOR = "poor"           # 较差
    BAD = "bad"             # 很差


class BufferState(Enum):
    """缓冲状态"""
    HEALTHY = "healthy"     # 健康
    MARGINAL = "marginal"   # 边缘
    STARVING = "starving"   # 不足
    OVER_BUFFERED = "over_buffered"  # 过度缓冲


@dataclass
class VodQualityMetrics:
    """点播质量指标"""
    # 基本信息
    record_id: str = ""
    source_url: str = ""
    timestamp: float = field(default_factory=time.time)

    # 视频质量
    bitrate_kbps: float = 0.0
    fps: float = 0.0
    frame_drop_rate: float = 0.0  # 丢帧率
    video_width: int = 0
    video_height: int = 0
    codec: str = ""

    # 网络质量
    latency_ms: float = 0.0
    download_speed_kbps: float = 0.0
    buffer_duration_ms: float = 0.0

    # 缓冲健康
    buffer_health: float = 1.0  # 0-1, 缓冲健康度
    buffer_state: BufferState = BufferState.HEALTHY

    # 播放状态
    current_time: float = 0.0
    duration: float = 0.0
    playback_speed: float = 1.0

    # 质量评估
    quality_level: QualityLevel = QualityLevel.GOOD
    score: float = 100.0  # 0-100 综合评分

    # 错误统计
    error_count: int = 0
    retry_count: int = 0
    last_error: str = ""


@dataclass
class VodSource:
    """点播源配置"""
    url: str
    protocol: str  # mp4, hls, flv, webrtc
    priority: int = 0  # 优先级，数字越小优先级越高
    bitrate: int = 0  # 预估码率
    available: bool = True
    last_check: float = 0  # 上次检查时间
    failure_count: int = 0  # 失败次数
    avg_latency_ms: float = 0  # 平均延迟


@dataclass
class VodSession:
    """点播会话"""
    session_id: str
    record_id: str
    device_id: str
    channel_id: str
    sources: list[VodSource]
    current_source_index: int = 0
    quality_metrics: VodQualityMetrics = field(default_factory=VodQualityMetrics)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_access: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "active"  # active, paused, ended, error


class VodQualityMonitor:
    """
    点播质量监控器
    
    核心功能：
    1. 实时质量采样
    2. 故障自动转移
    3. 缓冲自适应
    4. 画质动态调整
    """

    _instance: Optional['VodQualityMonitor'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 会话管理
        self._sessions: dict[str, VodSession] = {}
        self._sessions_lock = asyncio.Lock()

        # 质量指标缓存
        self._metrics_cache: dict[str, VodQualityMetrics] = {}

        # 质量采样任务
        self._sampling_tasks: dict[str, asyncio.Task] = {}

        # 回调函数
        self._quality_callbacks: dict[str, list[Callable]] = {}
        self._error_callbacks: dict[str, list[Callable]] = {}

        # 配置参数
        self.sampling_interval = 1.0  # 采样间隔(秒)
        self.quality_check_interval = 5.0  # 质量检查间隔
        self.buffer_health_threshold = 0.3  # 缓冲健康阈值
        self.min_buffer_ms = 500  # 最小缓冲
        self.max_buffer_ms = 5000  # 最大缓冲
        self.auto_switch_enabled = True  # 自动源切换
        self.quality_adaptation_enabled = True  # 画质自适应

        # 阈值配置
        self.quality_thresholds = {
            QualityLevel.EXCELLENT: 90,
            QualityLevel.GOOD: 70,
            QualityLevel.FAIR: 50,
            QualityLevel.POOR: 30,
        }

        # 统计信息
        self.stats = {
            'total_sessions': 0,
            'active_sessions': 0,
            'total_switches': 0,
            'total_retries': 0,
            'avg_quality_score': 0.0
        }

        # 启动后台任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info("VodQualityMonitor initialized")

    async def start(self):
        """启动监控服务"""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("VodQualityMonitor started")

    async def stop(self):
        """停止监控服务"""
        self._running = False

        # 停止所有采样任务
        for task in self._sampling_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # intentional: asyncio cancellation

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass  # intentional: asyncio cancellation

        # 清理会话
        self._sessions.clear()
        self._metrics_cache.clear()

        logger.info("VodQualityMonitor stopped")

    # ==================== 会话管理 ====================

    async def create_session(
        self,
        record_id: str,
        device_id: str,
        channel_id: str,
        sources: list[dict]
    ) -> str:
        """
        创建点播会话
        
        Args:
            record_id: 录像ID
            device_id: 设备ID
            channel_id: 通道ID
            sources: 源列表 [{url, protocol, bitrate, priority}, ...]
        
        Returns:
            session_id
        """
        import uuid
        session_id = str(uuid.uuid4())[:16]

        vod_sources = [
            VodSource(
                url=s.get('url', ''),
                protocol=s.get('protocol', 'mp4'),
                priority=s.get('priority', i),
                bitrate=s.get('bitrate', 0),
                available=True
            )
            for i, s in enumerate(sources)
        ]

        session = VodSession(
            session_id=session_id,
            record_id=record_id,
            device_id=device_id,
            channel_id=channel_id,
            sources=vod_sources,
            quality_metrics=VodQualityMetrics(record_id=record_id)
        )

        async with self._sessions_lock:
            self._sessions[session_id] = session

        self.stats['total_sessions'] += 1
        self.stats['active_sessions'] = len(self._sessions)

        logger.info(f"VodQualityMonitor: Session created {session_id} for record {record_id}")
        return session_id

    async def get_session(self, session_id: str) -> Optional[VodSession]:
        """获取会话"""
        async with self._sessions_lock:
            return self._sessions.get(session_id)

    async def close_session(self, session_id: str):
        """关闭会话"""
        async with self._sessions_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self.stats['active_sessions'] = len(self._sessions)
                logger.info(f"VodQualityMonitor: Session closed {session_id}")

    async def update_metrics(self, session_id: str, metrics: VodQualityMetrics):
        """
        更新质量指标
        
        Args:
            session_id: 会话ID
            metrics: 质量指标
        """
        session = await self.get_session(session_id)
        if not session:
            return

        # 更新会话指标
        session.quality_metrics = metrics
        session.last_access = datetime.now(timezone.utc)

        # 缓存最新指标
        self._metrics_cache[session_id] = metrics

        # 计算质量等级
        metrics.quality_level = self._calculate_quality_level(metrics)
        metrics.score = self._calculate_quality_score(metrics)

        # 检测并处理问题
        await self._check_and_adapt(session, metrics)

    # ==================== 质量计算 ====================

    def _calculate_quality_level(self, metrics: VodQualityMetrics) -> QualityLevel:
        """计算质量等级"""
        score = self._calculate_quality_score(metrics)

        for level, threshold in sorted(
            self.quality_thresholds.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            if score >= threshold:
                return level
        return QualityLevel.BAD

    def _calculate_quality_score(self, metrics: VodQualityMetrics) -> float:
        """计算质量评分 (0-100)"""
        score = 100.0

        # 帧率损失 (最多扣30分)
        if metrics.fps > 0:
            expected_fps = 25  # 假设25fps
            fps_ratio = metrics.fps / expected_fps
            if fps_ratio < 1:
                score -= (1 - fps_ratio) * 30

        # 丢帧率 (最多扣25分)
        if metrics.frame_drop_rate > 0:
            score -= min(25, metrics.frame_drop_rate * 25)

        # 缓冲健康 (最多扣20分)
        if metrics.buffer_health < self.buffer_health_threshold:
            score -= (self.buffer_health_threshold - metrics.buffer_health) * 66

        # 延迟影响 (最多扣15分)
        if metrics.latency_ms > 200:
            score -= min(15, (metrics.latency_ms - 200) / 20)

        # 错误惩罚 (每次错误扣5分)
        score -= min(10, metrics.error_count * 5)

        return max(0, min(100, score))

    # ==================== 自适应控制 ====================

    async def _check_and_adapt(self, session: VodSession, metrics: VodQualityMetrics):
        """检查并自适应调整"""
        if not self._running:
            return

        # 检查缓冲状态
        buffer_state = self._calculate_buffer_state(metrics)
        metrics.buffer_state = buffer_state

        # 缓冲不足处理
        if buffer_state == BufferState.STARVING and metrics.buffer_duration_ms < self.min_buffer_ms:
            logger.warning(
                f"VodQualityMonitor: Buffer starving for session {session.session_id}, "
                f"buffer={metrics.buffer_duration_ms:.0f}ms"
            )
            await self._handle_buffer_starving(session)

        # 质量下降处理
        if metrics.quality_level in [QualityLevel.POOR, QualityLevel.BAD]:
            logger.warning(
                f"VodQualityMonitor: Quality degradation for session {session.session_id}, "
                f"level={metrics.quality_level.value}, score={metrics.score:.1f}"
            )
            await self._handle_quality_degradation(session)

        # 错误处理
        if metrics.error_count > 3:
            logger.error(
                f"VodQualityMonitor: Too many errors for session {session.session_id}"
            )
            await self._handle_session_error(session)

    def _calculate_buffer_state(self, metrics: VodQualityMetrics) -> BufferState:
        """计算缓冲状态"""
        buffer_ms = metrics.buffer_duration_ms

        if buffer_ms >= self.max_buffer_ms:
            return BufferState.OVER_BUFFERED
        elif buffer_ms >= self.min_buffer_ms * 3:
            return BufferState.HEALTHY
        elif buffer_ms >= self.min_buffer_ms:
            return BufferState.MARGINAL
        else:
            return BufferState.STARVING

    async def _handle_buffer_starving(self, session: VodSession):
        """处理缓冲不足"""
        if not self.auto_switch_enabled:
            return

        # 尝试切换到更稳定的源
        next_source = self._find_next_available_source(session)
        if next_source:
            await self._switch_to_source(session, next_source)

    async def _handle_quality_degradation(self, session: VodSession):
        """处理质量下降"""
        if not self.quality_adaptation_enabled:
            return

        # 检查是否可以切换到更高质量的源
        current = session.sources[session.current_source_index] if session.sources else None
        if not current:
            return

        # 查找质量更好的源
        better_sources = [
            s for s in session.sources
            if s.priority < current.priority and s.available
        ]

        if better_sources:
            best = min(better_sources, key=lambda x: x.priority)
            await self._switch_to_source(session, best)

    async def _handle_session_error(self, session: VodSession):
        """处理会话错误"""
        # 标记当前源不可用
        if session.current_source_index < len(session.sources):
            session.sources[session.current_source_index].available = False

        # 尝试下一个源
        next_source = self._find_next_available_source(session)
        if next_source:
            await self._switch_to_source(session, next_source)
        else:
            session.status = "error"
            logger.error(
                f"VodQualityMonitor: No available sources for session {session.session_id}"
            )

    # ==================== 源切换 ====================

    def _find_next_available_source(self, session: VodSession) -> Optional[VodSource]:
        """查找下一个可用源"""
        available = [
            (i, s) for i, s in enumerate(session.sources)
            if s.available and i != session.current_source_index
        ]

        if not available:
            return None

        # 按优先级排序
        available.sort(key=lambda x: x[1].priority)
        return available[0][1]

    async def _switch_to_source(self, session: VodSession, source: VodSource):
        """切换到指定源"""
        old_index = session.current_source_index
        new_index = next(
            (i for i, s in enumerate(session.sources) if s.url == source.url),
            -1
        )

        if new_index == -1:
            return

        session.current_source_index = new_index
        session.quality_metrics.source_url = source.url
        self.stats['total_switches'] += 1

        logger.info(
            f"VodQualityMonitor: Switched source for session {session.session_id} "
            f"from index {old_index} to {new_index} ({source.url[:50]}...)"
        )

        # 触发回调
        await self._trigger_switch_callback(session, source)

    async def _trigger_switch_callback(self, session: VodSession, new_source: VodSource):
        """触发源切换回调"""
        session_id = session.session_id
        if session_id in self._quality_callbacks:
            for callback in self._quality_callbacks[session_id]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(session, new_source)
                    else:
                        callback(session, new_source)
                except Exception as e:
                    logger.error(f"VodQualityMonitor: Callback error: {e}")

    # ==================== 回调注册 ====================

    async def register_quality_callback(
        self,
        session_id: str,
        callback: Callable[[VodSession, VodSource], Awaitable[None]]
    ):
        """注册质量回调"""
        if session_id not in self._quality_callbacks:
            self._quality_callbacks[session_id] = []
        self._quality_callbacks[session_id].append(callback)

    async def register_error_callback(
        self,
        session_id: str,
        callback: Callable[[VodSession, str], Awaitable[None]]
    ):
        """注册错误回调"""
        if session_id not in self._error_callbacks:
            self._error_callbacks[session_id] = []
        self._error_callbacks[session_id].append(callback)

    async def unregister_callbacks(self, session_id: str):
        """取消注册所有回调"""
        self._quality_callbacks.pop(session_id, None)
        self._error_callbacks.pop(session_id, None)

    # ==================== 后台任务 ====================

    async def _cleanup_loop(self):
        """清理过期会话的后台任务"""
        while self._running:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                now = datetime.now(timezone.utc)
                async with self._sessions_lock:
                    to_remove = []

                    for session_id, session in self._sessions.items():
                        # 清理长时间未访问的会话
                        if (now - session.last_access).total_seconds() > 3600:
                            to_remove.append(session_id)

                    for session_id in to_remove:
                        del self._sessions[session_id]
                        self._metrics_cache.pop(session_id, None)

                    if to_remove:
                        logger.info(
                            f"VodQualityMonitor: Cleaned up {len(to_remove)} expired sessions"
                        )

                # 更新统计
                self._update_stats()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"VodQualityMonitor: Cleanup error: {e}")

    def _update_stats(self):
        """更新统计信息"""
        active_sessions = list(self._sessions.values())

        if active_sessions:
            total_score = sum(s.quality_metrics.score for s in active_sessions)
            count = len(active_sessions)
            self.stats['avg_quality_score'] = total_score / count if count > 0 else 0.0  # 防除零保护

        self.stats['active_sessions'] = len(active_sessions)

    # ==================== 公开 API ====================

    async def get_current_metrics(self, session_id: str) -> Optional[VodQualityMetrics]:
        """获取当前质量指标"""
        return self._metrics_cache.get(session_id)

    async def get_session_sources(self, session_id: str) -> list[VodSource]:
        """获取会话源列表"""
        session = await self.get_session(session_id)
        if not session:
            return []
        return session.sources

    async def report_error(self, session_id: str, error: str):
        """报告错误"""
        session = await self.get_session(session_id)
        if session:
            session.quality_metrics.error_count += 1
            session.quality_metrics.last_error = error

    async def report_retry(self, session_id: str):
        """报告重试"""
        session = await self.get_session(session_id)
        if session:
            session.quality_metrics.retry_count += 1
            self.stats['total_retries'] += 1

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self.stats,
            'cache_size': len(self._metrics_cache),
            'running': self._running
        }


# 单例实例
vod_quality_monitor = VodQualityMonitor()