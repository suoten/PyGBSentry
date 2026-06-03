"""
实时预览流媒体质量监控服务 - Stream Quality Monitor Service

专门针对实时预览场景优化，解决抖动、花屏问题。
"""

import asyncio
from loguru import logger
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable




class StreamHealthLevel(Enum):
    """流健康等级"""
    EXCELLENT = "excellent"  # 极好，无任何问题
    HEALTHY = "healthy"       # 健康，轻微波动
    DEGRADED = "degraded"    # 降级，有卡顿
    POOR = "poor"            # 较差，经常卡顿
    CRITICAL = "critical"     # 危险，可能断流


class StreamProtocol(Enum):
    """流协议"""
    RTSP = "rtsp"
    RTMP = "rtmp"
    HTTP_FLV = "http_flv"
    HLS = "hls"
    WEBRTC = "webrtc"
    UDP = "udp"
    TCP = "tcp"


@dataclass
class StreamQualitySample:
    """流质量采样"""
    timestamp: float = field(default_factory=time.time)

    # 基本信息
    stream_id: str = ""
    ssrc: str = ""
    protocol: str = ""

    # 视频质量
    fps: float = 0.0
    bitrate_kbps: float = 0.0
    video_width: int = 0
    video_height: int = 0
    codec: str = ""
    keyframe_interval: float = 0.0

    # 网络质量
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_rate: float = 0.0  # 丢包率 0-1
    bandwidth_kbps: float = 0.0

    # 缓冲状态
    buffer_ms: float = 0.0
    buffer_state: str = "unknown"  # healthy, marginal, starving

    # 错误统计
    dropped_frames: int = 0
    error_count: int = 0
    disconnect_count: int = 0

    # 计算指标
    health_score: float = 100.0  # 0-100 综合评分
    health_level: StreamHealthLevel = StreamHealthLevel.EXCELLENT


@dataclass
class StreamSession:
    """流会话"""
    session_id: str
    device_id: str
    channel_id: str

    # 协议信息
    protocol: StreamProtocol = StreamProtocol.HTTP_FLV
    transport: str = "TCP"  # UDP, TCP

    # 源信息
    source_ip: str = ""
    source_port: int = 0
    ssrc: str = ""

    # 质量历史
    samples: list[StreamQualitySample] = field(default_factory=list)
    latest_sample: Optional[StreamQualitySample] = None

    # 状态
    status: str = "connecting"  # connecting, active, degraded, reconnecting, stopped
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # 统计
    total_bytes: int = 0
    total_frames: int = 0
    uptime_seconds: float = 0.0


class StreamQualityMonitor:
    """
    实时预览流质量监控器
    
    核心功能：
    1. 实时质量采样与分析
    2. 抖动检测与平滑
    3. 花屏预警
    4. 自动重连优化
    5. 协议自适应
    """

    _instance: Optional['StreamQualityMonitor'] = None

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
        self._sessions: dict[str, StreamSession] = {}
        self._sessions_lock = asyncio.Lock()

        # 采样配置
        self.sampling_interval = 1.0  # 采样间隔(秒)
        self.sample_window_size = 30   # 采样窗口大小

        # 质量阈值
        self.thresholds = {
            'fps_min': 20,           # 最低 FPS
            'fps_drop_max': 5,        # 最大 FPS 波动
            'packet_loss_max': 0.02,   # 最大丢包率 2%
            'jitter_max': 50,        # 最大抖动 ms
            'latency_max': 1000,       # 最大延迟 ms
            'buffer_min': 500,        # 最小缓冲 ms
            'health_score_min': 70,   # 健康分最低阈值
        }

        # 统计
        self._stats = {
            'total_sessions': 0,
            'active_sessions': 0,
            'total_reconnects': 0,
            'avg_health_score': 0.0,
            'alerts_triggered': 0
        }

        # 回调函数
        self._quality_callbacks: dict[str, Callable] = {}
        self._alert_callbacks: list[Callable] = []

        # W-18 码率自适应切换冷却计时器，防止频繁切换导致振荡
        self._last_bitrate_switch_time: dict[str, float] = {}
        self._bitrate_switch_cooldown_seconds: float = 30.0

        logger.info("StreamQualityMonitor initialized")

    async def create_session(
        self,
        session_id: str,
        device_id: str,
        channel_id: str,
        protocol: str = "http_flv",
        transport: str = "TCP"
    ) -> StreamSession:
        """创建流会话"""
        session = StreamSession(
            session_id=session_id,
            device_id=device_id,
            channel_id=channel_id,
            protocol=StreamProtocol(protocol) if protocol in [p.value for p in StreamProtocol] else StreamProtocol.HTTP_FLV,
            transport=transport
        )

        async with self._sessions_lock:
            self._sessions[session_id] = session

        self._stats['total_sessions'] += 1
        self._stats['active_sessions'] = len(self._sessions)

        logger.info(f"StreamQualityMonitor: Session created {session_id} for {device_id}/{channel_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[StreamSession]:
        """获取会话"""
        async with self._sessions_lock:
            return self._sessions.get(session_id)

    async def close_session(self, session_id: str):
        """关闭会话"""
        async with self._sessions_lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = "stopped"
                del self._sessions[session_id]
                self._stats['active_sessions'] = len(self._sessions)
                # W-18 清理冷却计时器残留
                self._last_bitrate_switch_time.pop(session_id, None)
                logger.info(f"StreamQualityMonitor: Session closed {session_id}")

    async def add_sample(
        self,
        session_id: str,
        sample: StreamQualitySample
    ):
        """
        添加质量采样
        
        这是实时预览质量监控的核心方法。
        """
        session = await self.get_session(session_id)
        if not session:
            return

        # 分析采样
        analyzed_sample = self._analyze_sample(sample)

        # 更新会话
        session.latest_sample = analyzed_sample
        session.last_update = datetime.now(timezone.utc)

        # 维护采样历史
        session.samples.append(analyzed_sample)
        if len(session.samples) > self.sample_window_size:
            session.samples.pop(0)

        # 更新健康分
        analyzed_sample.health_score = self._calculate_health_score(session, analyzed_sample)
        analyzed_sample.health_level = self._determine_health_level(analyzed_sample.health_score)

        # 检测问题并触发回调
        await self._check_and_alert(session, analyzed_sample)

        # 触发质量回调
        if session_id in self._quality_callbacks:
            try:
                callback = self._quality_callbacks[session_id]
                if asyncio.iscoroutinefunction(callback):
                    await callback(session, analyzed_sample)
                else:
                    callback(session, analyzed_sample)
            except Exception as e:
                logger.error(f"StreamQualityMonitor: Callback error: {e}")

    def _analyze_sample(self, sample: StreamQualitySample) -> StreamQualitySample:
        """分析采样数据"""
        # 计算丢帧率
        if sample.total_frames > 0:
            sample.dropped_frames = max(0, sample.dropped_frames)

        # 判断缓冲状态
        if sample.buffer_ms >= 2000:
            sample.buffer_state = "healthy"
        elif sample.buffer_ms >= 1000:
            sample.buffer_state = "marginal"
        elif sample.buffer_ms >= 500:
            sample.buffer_state = "acceptable"
        else:
            sample.buffer_state = "starving"

        return sample

    def _calculate_health_score(
        self,
        session: StreamSession,
        sample: StreamQualitySample
    ) -> float:
        """
        计算综合健康评分 (0-100)
        
        评分规则：
        - 基准分 100
        - FPS 损失：每下降 1fps 扣 2 分
        - 丢包：每 1% 扣 5 分
        - 抖动：每 10ms 扣 1 分
        - 缓冲不足：扣 10-30 分
        - 错误：每次扣 5 分
        """
        score = 100.0

        # FPS 损失 (最多扣 30)
        expected_fps = 25.0  # 期望 25fps
        if sample.fps > 0:
            fps_diff = expected_fps - sample.fps
            if fps_diff > 0:
                score -= min(30, fps_diff * 2)

        # 丢包率 (最多扣 25)
        if sample.packet_loss_rate > 0:
            score -= min(25, sample.packet_loss_rate * 100 * 2)

        # 抖动 (最多扣 15)
        if sample.jitter_ms > 0:
            score -= min(15, sample.jitter_ms / 10)

        # 延迟 (最多扣 15)
        if sample.latency_ms > 200:
            excess = sample.latency_ms - 200
            score -= min(15, excess / 100)

        # 缓冲不足 (最多扣 15)
        if sample.buffer_ms < self.thresholds['buffer_min']:
            deficit = self.thresholds['buffer_min'] - sample.buffer_ms
            score -= min(15, deficit / 50)

        # 错误惩罚 (最多扣 10)
        score -= min(10, sample.error_count * 5)

        return max(0, min(100, score))

    def _determine_health_level(self, score: float) -> StreamHealthLevel:
        """确定健康等级"""
        if score >= 90:
            return StreamHealthLevel.EXCELLENT
        elif score >= 80:
            return StreamHealthLevel.HEALTHY
        elif score >= 60:
            return StreamHealthLevel.DEGRADED
        elif score >= 40:
            return StreamHealthLevel.POOR
        else:
            return StreamHealthLevel.CRITICAL

    async def _check_and_alert(
        self,
        session: StreamSession,
        sample: StreamQualitySample
    ):
        """检查并触发告警"""
        alerts = []

        # FPS 过低
        if sample.fps > 0 and sample.fps < self.thresholds['fps_min']:
            alerts.append({
                'type': 'fps_low',
                'level': 'warning',
                'message': f"FPS 过低: {sample.fps:.1f}",
                'suggestion': '可能存在网络抖动或编码器问题'
            })

        # 丢包率过高
        if sample.packet_loss_rate > self.thresholds['packet_loss_max']:
            alerts.append({
                'type': 'packet_loss',
                'level': 'warning',
                'message': f"丢包率过高: {sample.packet_loss_rate * 100:.2f}%",
                'suggestion': '检查网络质量，考虑切换到 TCP 协议'
            })

        # 缓冲不足
        if sample.buffer_ms < self.thresholds['buffer_min']:
            alerts.append({
                'type': 'buffer_starving',
                'level': 'critical' if sample.buffer_ms < 200 else 'warning',
                'message': f"缓冲不足: {sample.buffer_ms:.0f}ms",
                'suggestion': '降低码率或增加缓冲时间'
            })

        # 健康分过低
        if sample.health_score < self.thresholds['health_score_min']:
            alerts.append({
                'type': 'health_low',
                'level': 'critical',
                'message': f"健康分过低: {sample.health_score:.1f}",
                'suggestion': '建议切换到更稳定的协议或线路'
            })

        # 触发告警
        if alerts:
            self._stats['alerts_triggered'] += len(alerts)

            for alert in alerts:
                logger.warning(
                    f"StreamQualityMonitor: Alert for {session.session_id}: "
                    f"{alert['type']} - {alert['message']}"
                )

                for callback in self._alert_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(session, sample, alert)
                        else:
                            callback(session, sample, alert)
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")

        # W-18 码流自适应切换 — 质量降级时触发自动切换，加入冷却期防止振荡
        if sample.health_score < 40 and session.session_id:
            now = time.time()
            last_switch = self._last_bitrate_switch_time.get(session.session_id, 0.0)
            if now - last_switch >= self._bitrate_switch_cooldown_seconds:
                try:
                    from app.services.stream_strategy import stream_strategy
                    from app.db.session import AsyncSessionLocal
                    async with AsyncSessionLocal() as db:
                        await stream_strategy.auto_switch_bitrate(session.session_id, db)
                    self._last_bitrate_switch_time[session.session_id] = now
                except Exception as e:
                    logger.debug(f"Auto bitrate switch failed: {e}")
            else:
                logger.debug(f"Bitrate switch cooldown active for {session.session_id}, skipping")

    async def register_quality_callback(
        self,
        session_id: str,
        callback: Callable
    ):
        """注册质量回调"""
        self._quality_callbacks[session_id] = callback

    async def unregister_quality_callback(self, session_id: str):
        """取消注册质量回调"""
        self._quality_callbacks.pop(session_id, None)

    async def register_alert_callback(self, callback: Callable):
        """注册告警回调"""
        if callback not in self._alert_callbacks:
            self._alert_callbacks.append(callback)

    async def unregister_alert_callback(self, callback: Callable):
        """取消注册告警回调"""
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            'session_count': len(self._sessions),
            'thresholds': self.thresholds
        }

    async def get_dashboard_snapshot(self, per_session_sample_limit: int = 30) -> dict:
        """获取看板快照（会话最新状态 + 近期样本）"""
        limit = max(1, min(int(per_session_sample_limit or 30), 120))
        async with self._sessions_lock:
            sessions: list[dict] = []
            for session in self._sessions.values():
                latest = session.latest_sample
                latest_dict = None
                if latest:
                    latest_dict = {
                        "health_score": latest.health_score,
                        "health_level": latest.health_level.value if latest.health_level else "unknown",
                        "fps": latest.fps,
                        "bitrate_kbps": latest.bitrate_kbps,
                        "packet_loss_rate": latest.packet_loss_rate,
                        "buffer_ms": latest.buffer_ms,
                        "latency_ms": latest.latency_ms,
                        "timestamp": latest.timestamp,
                    }
                samples = session.samples[-limit:] if session.samples else []
                sessions.append(
                    {
                        "session_id": session.session_id,
                        "device_id": session.device_id,
                        "channel_id": session.channel_id,
                        "status": session.status,
                        "latest": latest_dict,
                        "samples": [
                            {
                                "timestamp": s.timestamp,
                                "health_score": s.health_score,
                                "health_level": s.health_level.value if s.health_level else "unknown",
                                "fps": s.fps,
                                "bitrate_kbps": s.bitrate_kbps,
                                "packet_loss_rate": s.packet_loss_rate,
                                "buffer_ms": s.buffer_ms,
                                "latency_ms": s.latency_ms,
                            }
                            for s in samples
                        ],
                    }
                )
            return {"sessions": sessions, "total_sessions": len(sessions)}

    async def get_session_health(self, session_id: str) -> Optional[dict]:
        """获取会话健康状态"""
        session = await self.get_session(session_id)
        if not session or not session.latest_sample:
            return None

        sample = session.latest_sample

        return {
            'session_id': session_id,
            'status': session.status,
            'health_score': sample.health_score,
            'health_level': sample.health_level.value,
            'fps': sample.fps,
            'bitrate_kbps': sample.bitrate_kbps,
            'packet_loss_rate': sample.packet_loss_rate,
            'jitter_ms': sample.jitter_ms,
            'buffer_ms': sample.buffer_ms,
            'buffer_state': sample.buffer_state,
            'latency_ms': sample.latency_ms,
            'resolution': f"{sample.video_width}x{sample.video_height}",
            'uptime_seconds': session.uptime_seconds,
            'recommendations': self._get_recommendations(session, sample)
        }

    def _get_recommendations(
        self,
        session: StreamSession,
        sample: StreamQualitySample
    ) -> list[str]:
        """获取优化建议"""
        recommendations = []

        if sample.fps < self.thresholds['fps_min']:
            recommendations.append("建议降低视频码率或切换到主码流")

        if sample.packet_loss_rate > self.thresholds['packet_loss_max']:
            recommendations.append("建议切换到 TCP 协议，UDP 在不稳定网络下丢包严重")

        if sample.jitter_ms > self.thresholds['jitter_max']:
            recommendations.append("网络抖动较大，建议启用流量整形或增加缓冲")

        if sample.buffer_ms < self.thresholds['buffer_min']:
            recommendations.append("建议增加播放器缓冲时间(当前 bufferTime 参数)")

        if sample.health_score < 60:
            recommendations.append("整体质量较差，建议检查网络或设备状态")

        if not recommendations:
            recommendations.append("当前播放质量良好")

        return recommendations

    async def report_reconnect(self, session_id: str):
        """报告重连事件"""
        session = await self.get_session(session_id)
        if session:
            self._stats['total_reconnects'] += 1
            session.status = "reconnecting"
            if session.latest_sample:
                session.latest_sample.disconnect_count += 1


# 单例
stream_quality_monitor = StreamQualityMonitor()
