"""
点播源智能选择与质量控制服务

功能：
1. 智能源优先级排序
2. 多源故障自动转移
3. 码率与质量预测
4. 预加载优化
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger  # FIX: [2026-07-13] 缺少 logger 导入导致 vod 端点导入失败 [全栈工程师]
from typing import Optional, Any
import hashlib


@dataclass
class VodSourceCandidate:
    """点播源候选"""
    # 基本信息
    url: str
    protocol: str  # mp4, hls, flv, webrtc, rtsp, rtmp
    source_type: str  # local, cdn, s3, http
    
    # 质量属性
    priority: int = 0  # 用户/系统优先级
    estimated_bitrate: int = 0  # 预估码率 (kbps)
    estimated_quality: str = "unknown"  # low, medium, high, ultra
    
    # 可用性
    available: bool = True
    health_score: float = 100.0  # 健康分 0-100
    last_check_at: float = 0  # 上次检查时间
    response_time_ms: float = 0  # 响应时间
    check_count: int = 0  # 检查次数
    consecutive_failures: int = 0  # 连续失败次数
    
    # 元数据
    content_length: int = 0  # 文件大小
    content_type: str = ""  # MIME类型
    supports_range: bool = False  # 是否支持 Range 请求


class VodSourceSelector:
    """
    点播源智能选择器
    
    选择策略：
    1. 优先本地/内网源
    2. 考虑码率和质量
    3. 健康分淘汰
    4. 响应时间加权
    """
    
    _instance: Optional['VodSourceSelector'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 协议优先级映射 (数字越小优先级越高)
        self.protocol_priority = {
            'local': 0,      # 本地文件
            'internal': 1,   # 内网地址
            'webrtc': 2,     # WebRTC
            'rtmp': 3,       # RTMP
            'rtsp': 4,      # RTSP
            'hls': 5,       # HLS
            'flv': 6,       # FLV
            'mp4': 7,       # MP4直连
            'http': 8,      # 其他HTTP
        }
        
        # 质量优先级
        self.quality_priority = {
            'ultra': 0,   # 4K+
            'high': 1,   # 1080p
            'medium': 2, # 720p
            'low': 3,    # 480p及以下
            'unknown': 4,
        }
        
        # 配置
        self.max_check_concurrency = 5  # 最大并发检查数
        self.check_timeout_ms = 3000  # 检查超时
        self.health_score_threshold = 60  # 健康分阈值
        self.max_consecutive_failures = 3  # 最大连续失败次数
        self.cache_duration_seconds = 30  # 缓存时间
        
        # 检查缓存
        self._check_cache: dict[str, dict] = {}
        self._check_semaphore = asyncio.Semaphore(self.max_check_concurrency)
        self._cache_lock = asyncio.Lock()  # W-01 保护 _check_cache 的并发读写
        self._cache_cleanup_threshold = 1000  # M-13 添加缓存清理机制
        
        logger.info("VodSourceSelector initialized")

    def _cleanup_expired_cache(self):
        """Remove expired cache entries when cache size exceeds threshold."""
        if len(self._check_cache) <= self._cache_cleanup_threshold:
            return
        now = time.time()
        expired_keys = [
            k for k, v in self._check_cache.items()
            if now - v.get('timestamp', 0) >= self.cache_duration_seconds
        ]
        for k in expired_keys:
            del self._check_cache[k]
        if expired_keys:
            logger.debug(f"Cache cleanup: removed {len(expired_keys)} expired entries, remaining: {len(self._check_cache)}")

    async def select_best_source(
        self,
        sources: list[dict],
        prefer_protocol: Optional[str] = None,
        prefer_quality: Optional[str] = None,
        network_condition: str = "good"  # good, fair, poor
    ) -> dict:
        """
        选择最优源
        
        Args:
            sources: 源列表 [{url, protocol, priority?, bitrate?, ...}, ...]
            prefer_protocol: 偏好协议
            prefer_quality: 偏好质量
            network_condition: 网络状况
        
        Returns:
            最佳源配置
        """
        candidates = []
        
        # 转换为候选对象
        for i, src in enumerate(sources):
            candidate = self._create_candidate(src, i)
            candidates.append(candidate)
        
        # 检查可用性 (并行)
        await self._check_sources_concurrent(candidates)
        
        # 过滤不可用源
        available = [c for c in candidates if c.available]
        if not available:
            # 如果没有可用源，返回第一个并标记
            if candidates:
                candidates[0].available = True  # 强制可用
                return self._to_source_dict(candidates[0])
            return {}
        
        # 计算综合评分
        for candidate in available:
            candidate.health_score = self._calculate_health_score(
                candidate, network_condition
            )
        
        # 排序选择
        available.sort(key=lambda x: (
            # 1. 可用性 (不可用排最后)
            -x.available,
            # 2. 健康分
            -x.health_score,
            # 3. 协议优先级
            self.protocol_priority.get(x.source_type, 99),
            self.protocol_priority.get(x.protocol, 99),
            # 4. 质量优先级
            self.quality_priority.get(x.estimated_quality, 99),
            # 5. 码率 (高优先)
            -x.estimated_bitrate,
            # 6. 响应时间
            x.response_time_ms,
            # 7. 用户优先级
            x.priority,
        ))
        
        best = available[0]
        logger.info(
            f"VodSourceSelector: Selected source {best.url[:50]}... "
            f"(protocol={best.protocol}, health={best.health_score:.1f}, "
            f"response={best.response_time_ms:.0f}ms)"
        )
        
        return self._to_source_dict(best)
    
    def _create_candidate(self, source: dict, index: int) -> VodSourceCandidate:
        """从字典创建候选对象"""
        url = source.get('url', '')
        protocol = source.get('protocol', self._detect_protocol(url))
        source_type = self._classify_source_type(url)
        
        return VodSourceCandidate(
            url=url,
            protocol=protocol,
            source_type=source_type,
            priority=source.get('priority', index),
            estimated_bitrate=source.get('bitrate', source.get('estimated_bitrate', 0)),
            estimated_quality=source.get('quality', 'unknown'),
        )
    
    def _detect_protocol(self, url: str) -> str:
        """检测协议"""
        url_lower = url.lower()
        if url_lower.endswith('.m3u8') or '/hls/' in url_lower:
            return 'hls'
        if url_lower.endswith('.flv') or '/flv/' in url_lower:
            return 'flv'
        if url_lower.endswith('.mp4') or '/record/' in url_lower or '/mp4/' in url_lower:
            return 'mp4'
        if '/webrtc/' in url_lower or 'api/webrtc' in url_lower:
            return 'webrtc'
        if url_lower.startswith('rtmp://'):
            return 'rtmp'
        if url_lower.startswith('rtsp://'):
            return 'rtsp'
        return 'http'
    
    def _classify_source_type(self, url: str) -> str:
        """分类源类型"""
        url_lower = url.lower()
        
        # 本地文件
        if url_lower.startswith('/') or ':\\' in url:
            return 'local'
        
        # S3/MinIO
        if 's3://' in url_lower or 'minio' in url_lower:
            return 's3'
        
        # 内网地址
        parsed = self._parse_url(url)
        if parsed:
            host = parsed.get('host', '').lower()
            if any(x in host for x in ['192.168.', '10.', '172.', 'localhost', '127.0.0.1']):
                return 'internal'
        
        # CDN/HTTP
        return 'http'
    
    def _parse_url(self, url: str) -> dict:
        """简单URL解析"""
        try:
            from urllib.parse import urlparse
            result = urlparse(url)
            return {
                'scheme': result.scheme,
                'host': result.netloc,
                'path': result.path,
                'query': result.query,
            }
        except Exception:
            return {}
    
    async def _check_sources_concurrent(self, candidates: list[VodSourceCandidate]):
        """并发检查源可用性"""
        tasks = [self._check_single_source(c) for c in candidates]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_single_source(self, candidate: VodSourceCandidate):
        """检查单个源"""
        cache_key = self._get_cache_key(candidate.url)
        
        # 检查缓存（读操作加锁防止与清理线程冲突）
        async with self._cache_lock:
            cached = self._check_cache.get(cache_key)
            if cached:
                elapsed = time.time() - cached['timestamp']
                if elapsed < self.cache_duration_seconds:
                    candidate.available = cached['available']
                    candidate.health_score = cached['health_score']
                    candidate.response_time_ms = cached['response_time_ms']
                    return
        
        # 并发控制
        async with self._check_semaphore:
            start = time.time()
            try:
                async with asyncio.timeout(self.check_timeout_ms / 1000):
                    available, response_time = await self._probe_url(candidate.url)
                    
                    candidate.available = available
                    candidate.response_time_ms = response_time
                    candidate.last_check_at = time.time()
                    candidate.check_count += 1
                    
                    if not available:
                        candidate.consecutive_failures += 1
                    else:
                        candidate.consecutive_failures = 0
                    
                    # 标记不可用
                    if candidate.consecutive_failures >= self.max_consecutive_failures:
                        candidate.available = False
                    
            except asyncio.TimeoutError:
                candidate.available = False
                candidate.response_time_ms = self.check_timeout_ms
                candidate.consecutive_failures += 1
            except Exception as e:
                candidate.available = False
                candidate.response_time_ms = self.check_timeout_ms
                candidate.consecutive_failures += 1
                logger.debug(f"Source check error: {e}")
        
        # 更新缓存
        self._check_cache[cache_key] = {
            'available': candidate.available,
            'health_score': candidate.health_score,
            'response_time_ms': candidate.response_time_ms,
            'timestamp': time.time(),
        }
        self._cleanup_expired_cache()
    
    async def _probe_url(self, url: str) -> tuple[bool, float]:
        """探测URL可用性"""
        start = time.time()
        
        url_lower = url.lower()
        
        # 本地文件直接检查
        if url_lower.startswith('/') or ':\\' in url_lower:
            import os
            exists = os.path.exists(url)
            return exists, (time.time() - start) * 1000
        
        # S3 特殊处理
        if url_lower.startswith('s3://'):
            return True, (time.time() - start) * 1000
        
        # HTTP/HTTPS HEAD请求
        try:
            from app.core.http_client import get_http_client
            client = await get_http_client()
            resp = await client.head(url, timeout=5.0, follow_redirects=True)
            response_time = (time.time() - start) * 1000
            
            content_type = resp.headers.get('Content-Type', '').lower()
            supported_types = ['video/', 'application/', 'audio/']
            is_video = any(t in content_type for t in supported_types)
            
            content_length = int(resp.headers.get('Content-Length', 0))
            
            return is_video or content_length > 0, response_time
                
        except Exception:
            return False, (time.time() - start) * 1000
    
    def _calculate_health_score(
        self,
        candidate: VodSourceCandidate,
        network_condition: str
    ) -> float:
        """计算健康分"""
        score = 100.0
        
        # 响应时间评分 (最多扣40分)
        response_time = candidate.response_time_ms
        if response_time > 0:
            if response_time < 100:
                pass  # 优秀
            elif response_time < 500:
                score -= 10
            elif response_time < 1000:
                score -= 20
            elif response_time < 2000:
                score -= 30
            else:
                score -= 40
        
        # 连续失败惩罚 (最多扣30分)
        score -= min(30, candidate.consecutive_failures * 10)
        
        # 协议类型加成
        if candidate.source_type in ['local', 'internal']:
            score += 10
        
        # 网络状况影响
        if network_condition == 'poor':
            # 网络差时优先考虑稳定性
            if candidate.protocol in ['hls', 'flv']:  # 这些协议有缓冲
                score += 5
        elif network_condition == 'good':
            # 网络好时优先考虑延迟
            if candidate.protocol == 'webrtc':
                score += 10
            elif candidate.protocol == 'mp4':
                score += 5
        
        # 码率加成 (高码率通常意味着高画质)
        if candidate.estimated_bitrate > 4000:
            score += 5
        elif candidate.estimated_bitrate > 2000:
            score += 3
        
        return max(0, min(100, score))
    
    def _get_cache_key(self, url: str) -> str:
        """获取缓存键"""
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def _to_source_dict(self, candidate: VodSourceCandidate) -> dict:
        """转换为源字典"""
        return {
            'url': candidate.url,
            'protocol': candidate.protocol,
            'source_type': candidate.source_type,
            'available': candidate.available,
            'health_score': candidate.health_score,
            'response_time_ms': candidate.response_time_ms,
            'estimated_bitrate': candidate.estimated_bitrate,
            'quality': candidate.estimated_quality,
        }
    
    def clear_cache(self):
        """清空检查缓存"""
        self._check_cache.clear()
        logger.info("VodSourceSelector: Cache cleared")


# 单例
vod_source_selector = VodSourceSelector()
