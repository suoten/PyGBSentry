"""
实时预览点播链路优化指南 - PyGBSentry 开源版

========================================
一、问题分析与解决思路
========================================

实时预览中常见的质量问题：

1. 抖动（画面卡顿、不流畅）
   原因：网络波动、缓冲不足、丢包
   解决：增加缓冲、优化协议选择

2. 花屏（画面出现马赛克、色彩异常）
   原因：丢帧、关键帧丢失、编码问题
   解决：TCP协议、增加缓冲容错

3. 首帧慢（打开慢）
   原因：信令延迟、协议握手
   解决：预连接、选择低延迟协议

========================================
二、核心组件说明
========================================

前端组件：
---------
1. EnhancedStreamPlayer.vue
   - 增强版实时预览播放器
   - 支持多协议：FLV、HLS、WebRTC
   - 自适应缓冲（防抖动）
   - 自动重连
   - 质量统计

2. 优化点：
   - 默认 1 秒缓冲（防抖动关键）
   - 使用 GPU 解码（更稳定）
   - 错误自动降级
   - 多线路自动切换

后端服务：
---------
1. stream_quality_monitor.py
   - 流质量实时监控
   - 抖动检测
   - 花屏预警
   - 健康评分

2. stream_optimization.py
   - 智能协议选择
   - 线路管理
   - 优化建议

========================================
三、协议选择策略
========================================

┌──────────────┬─────────────┬────────────┬───────────────────────────────┐
│    协议      │   延迟      │   稳定性   │         适用场景              │
├──────────────┼─────────────┼────────────┼───────────────────────────────┤
│ HTTP-FLV    │ 低(1-3s)  │   高      │ 实时预览首选，推荐使用          │
│ HLS         │ 中(3-10s) │   极高    │ 兼容性要求高、网络不稳        │
│ WebRTC      │ 极低(<1s)  │   中      │ 超低延迟，需HTTPS，极端场景    │
│ RTSP        │ 低         │   取决于网络│ 设备直连，兼容性稍差          │
└──────────────┴─────────────┴────────────┴───────────────────────────────┘

推荐协议栈：
1. HTTP-FLV > HLS > WebRTC
2. TCP > UDP（UDP丢包是花屏主因！）

========================================
四、播放器配置优化
========================================

Jessibuca 配置（FLV 播放）：

```javascript
const jessibuca = new Jessibuca({
    // 缓冲配置（防抖动关键！）
    bufferTime: 1000,        // 1秒缓冲，平衡延迟与稳定性
    // bufferTime: 500,      // 低延迟模式
    // bufferTime: 2000,     // 超稳定模式
    
    // 解码配置
    useWCS: false,           // 使用 MSE 解码
    decoder: 'gm',           // GPU 解码
    
    // 性能
    workloadLevel: 1,         // 低负载模式
})
```

HLS 配置：

```javascript
const hls = new Hls({
    // 关闭低延迟模式（点播/预览不需要低延迟）
    lowLatencyMode: false,
    
    // 缓冲配置
    backBufferLength: 30,     // 回退缓冲30秒
    maxBufferLength: 30,      // 最大缓冲30秒
    
    // 加载控制
    fragLoadingTimeOut: 20000,  // 分片加载超时
    fragLoadingMaxRetry: 3,     // 重试次数
    
    // 错误恢复
    autoRecover: true,
})
```

========================================
五、网络传输优化
========================================

1. ZLMediaKit 配置优化

[protocol]
# 启用 TCP 模式（比 UDP 更稳定）
tcp_mode = 1

# RTP 校验（关闭可减少花屏）
check_source = 0

[rtp_proxy]
# 使用 TCP 代理
rtp_type = 1

2. Nginx 配置（如果使用反向代理）

http {
    # 代理缓冲
    proxy_buffering on;
    proxy_buffer_size 128k;
    proxy_buffers 8 256k;
    
    # 超时
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}

3. 跨域配置

location / {
    # CORS
    add_header Access-Control-Allow-Origin *;
    add_header Access-Control-Allow-Methods 'GET, POST, OPTIONS';
    add_header Access-Control-Allow-Headers 'Range, Content-Type';
    
    # 预检请求
    if ($request_method = 'OPTIONS') {
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods 'GET, POST, OPTIONS';
        add_header Access-Control-Allow-Headers 'Range, Content-Type';
        add_header Access-Control-Max-Age 1728000;
        add_header Content-Type 'text/plain charset=UTF-8';
        add_header Content-Length 0;
        return 204;
    }
}

========================================
六、花屏问题排查
========================================

1. UDP 丢包（最常见）
   症状：画面出现马赛克、色彩块
   解决：切换到 TCP 协议

2. 关键帧丢失
   症状：花屏后恢复慢
   解决：
   - 检查设备 GOP 设置（建议 1-2秒）
   - 增加播放器容错

3. 网络抖动
   症状：间歇性花屏
   解决：
   - 增加缓冲时间
   - 启用自动重连

4. 编码器问题
   症状：持续花屏
   解决：
   - 切换到子码流
   - 检查设备编码设置

========================================
七、API 接口说明
========================================

1. 优化的实时预览播放
   GET /api/v1/stream-opt/play/{device_id}/{channel_id}
   
   参数：
   - protocol_preference: 协议偏好 (auto/flv/hls/webrtc)
   - quality_mode: 画质模式 (high/balance/stable)
   - enable_tcp_fallback: 启用TCP降级

2. 质量上报
   POST /api/v1/stream-opt/quality-report
   
   上报内容：
   - fps: 帧率
   - bitrate: 码率
   - packet_loss_rate: 丢包率
   - buffer_ms: 缓冲时间
   - jitter_ms: 抖动

3. 获取流健康状态
   GET /api/v1/stream-opt/health/{session_id}
   
   返回：
   - health_score: 健康评分 (0-100)
   - health_level: 健康等级
   - recommendations: 优化建议

4. 获取播放线路
   GET /api/v1/stream-opt/lines/{device_id}/{channel_id}
   
   返回：
   - lines: 线路列表
   - recommended: 推荐线路

5. 优化建议
   GET /api/v1/stream-opt/optimization-tips

========================================
八、环境变量配置
========================================

#.env 配置

# 流传输优化
STREAM_DEFAULT_PROTOCOL=http_flv
STREAM_BUFFER_TIME_MS=1000
STREAM_ENABLE_AUTO_RECONNECT=true
STREAM_TCP_FALLBACK=true

# 质量阈值
STREAM_MIN_FPS=20
STREAM_MAX_PACKET_LOSS_RATE=0.02
STREAM_MIN_BUFFER_MS=500
STREAM_HEALTH_SCORE_MIN=70

# ZLMediaKit
MEDIA_SERVER_PROTOCOL=tcp
MEDIA_SERVER_HTTP_PORT=8880
MEDIA_SERVER_SECRET=your_secret

========================================
九、性能监控
========================================

关键指标：
- FPS：帧率，应 > 20
- 丢包率：应 < 2%
- 缓冲时间：应 > 500ms
- 健康评分：应 > 70

健康等级：
- EXCELLENT (90-100): 极好
- HEALTHY (80-89): 良好
- DEGRADED (60-79): 降级
- POOR (40-59): 较差
- CRITICAL (0-39): 危险

自动处理：
- 缓冲不足：增加缓冲时间
- 花屏：切换到 TCP 协议
- 频繁断流：建议降低码率

========================================
十、故障排查清单
========================================

□ 1. 画面卡顿/抖动
   - 检查网络带宽
   - 增加 bufferTime 到 1000ms
   - 切换到 TCP 协议

□ 2. 花屏/马赛克
   - 切换到 TCP 协议（UDP 丢包）
   - 检查设备 GOP 设置
   - 切换到子码流

□ 3. 打开慢/首帧慢
   - 检查设备响应时间
   - 使用 HTTP-FLV 协议
   - 预连接优化

□ 4. 频繁断流
   - 启用自动重连
   - 检查网络稳定性
   - 降低码率使用子码流

□ 5. 兼容性差
   - 使用 HLS 协议
   - 检查跨域配置
   - 确认 HTTPS 配置（WebRTC）
"""

# 配置示例
STREAM_OPTIMIZATION_EXAMPLE = """
# .env 配置示例 - 实时预览优化

# ========== 传输优化 ==========
STREAM_DEFAULT_PROTOCOL=http_flv
STREAM_BUFFER_TIME_MS=1000
STREAM_ENABLE_AUTO_RECONNECT=true
STREAM_TCP_FALLBACK=true

# ========== 质量模式 ==========
# high: 高清模式，优先质量
# balance: 均衡模式，平衡延迟与稳定
# stable: 稳定模式，优先稳定

STREAM_QUALITY_MODE=balance

# ========== 协议偏好 ==========
# auto: 自动选择
# http_flv: HTTP-FLV（推荐）
# hls: HLS（兼容性最好）
# webrtc: WebRTC（最低延迟）

STREAM_PROTOCOL_PREFERENCE=auto

# ========== ZLMediaKit ==========
MEDIA_SERVER_HOST=127.0.0.1
MEDIA_SERVER_HTTP_PORT=8880
MEDIA_SERVER_SECRET=your_secret_here
MEDIA_SERVER_PROTOCOL=tcp
"""
