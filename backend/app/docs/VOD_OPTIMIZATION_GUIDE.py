"""
点播链路优化指南 - PyGBSentry 开源版

========================================
一、系统架构概览
========================================

点播链路包含以下核心组件：

┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │EnhancedVodPlayer│  │RecordList       │  │ QualityMonitor│ │
│  │ 增强点播播放器   │  │ 增强录像列表     │  │ 质量监控      │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │
│           │                    │                    │         │
└───────────┼────────────────────┼────────────────────┼─────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                      后端 API (FastAPI)                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   vod.py        │  │  vod_source_    │  │ vod_quality_ │ │
│  │  点播API端点     │  │  selector.py    │  │ monitor.py   │ │
│  │                  │  │  智能源选择器     │  │ 质量监控器    │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │
│           │                    │                    │         │
└───────────┼────────────────────┼────────────────────┼─────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                   存储层                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ ZLM本地文件  │  │  S3/MinIO   │  │  CDN                 │ │
│  │  /record/   │  │  云存储      │  │  (可选)              │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

========================================
二、核心文件说明
========================================

前端组件：
---------
1. src/components/EnhancedVodPlayer.vue
   - 增强版点播播放器
   - 支持 MP4、HLS、FLV、WebRTC
   - 自适应缓冲控制
   - 画质选择与平滑切换
   - 键盘快捷键支持

2. src/components/EnhancedCloudRecordList.vue
   - 增强版云端录像列表
   - 时间轴可视化
   - 批量操作
   - 录像质量统计

3. src/types/vod.d.ts
   - TypeScript 类型定义
   - 点播相关接口

后端服务：
---------
1. app/api/v1/endpoints/vod.py
   - 点播播放API
   - 智能源选择
   - 质量上报

2. app/services/vod_source_selector.py
   - 智能源选择器
   - 多源健康检查
   - 故障自动转移

3. app/services/vod_quality_monitor.py
   - 质量监控器
   - 缓冲自适应
   - 指标收集

========================================
三、优化配置清单
========================================

1. ZLMediaKit 配置优化
----------------------
编辑 binaries/linux64/config.ini 或对应配置文件：

[record]
# 录像分片大小(秒)，建议 300-600 秒
fileSecond = 300

# 录像采样间隔(毫秒)，建议 500ms
sampleMS = 500

[protocol]
# MP4 最大时长(秒)，建议与 fileSecond 相同
mp4_max_second = 300

# 开启快速启动
fast_start = 1

# 开启 moov 头优化
mov_fast_start = 1

[http]
# 开启 gzip 压缩
gzip = 1

# CORS 配置
cors = *

2. Nginx 优化配置（如果使用反向代理）
----------------------------------------

http {
    # Gzip 压缩
    gzip on;
    gzip_types video/mp4 video/webm video/ogg;
    gzip_min_length 1000;
    
    # 缓存控制
    proxy_buffering on;
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    
    # 超时配置
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Range 请求支持（点播必须）
    proxy_force_ranges on;
}

server {
    # 录像目录代理
    location /record/ {
        proxy_pass http://zlm_backend:8880;
        proxy_buffering on;
        
        # 允许 Range 请求
        proxy_force_ranges on;
        
        # 缓存配置
        proxy_cache_valid 200 60m;
        add_header X-Cache-Status $upstream_cache_status;
        
        # CORS
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods 'GET, OPTIONS';
        add_header Access-Control-Allow-Headers 'Range';
    }
}

3. 前端播放器配置
-----------------
在 EnhancedVodPlayer.vue 中可调整：

// 缓冲配置
const bufferConfig = {
    minBufferTime: 500,      // 最小缓冲时间(ms)
    maxBufferTime: 5000,     // 最大缓冲时间(ms)
    startBufferTime: 1000,   // 起始缓冲时间(ms)
    bufferHealthThreshold: 0.3 // 缓冲健康阈值
}

// HLS 配置
const hlsConfig = {
    enableWorker: true,           // 启用 Web Worker
    lowLatencyMode: false,        // 低延迟模式（点播关闭）
    backBufferLength: 30,          // 回退缓冲时长
    maxBufferLength: 30,          // 最大缓冲时长
    startLevel: -1,               // 自动选择
    fragLoadingTimeOut: 20000,     // 分片加载超时
    levelLoadingTimeOut: 10000    // 等级加载超时
}

// FLV 配置
const flvConfig = {
    enableWorker: true,
    stashInitialSize: 128,        // 初始缓冲
    lazyLoad: true,               // 懒加载
    maxBufferLength: 30,          // 最大缓冲
    autoCleanupSourceBuffer: true
}

4. 后端环境变量配置
-------------------
#.env 文件

# 点播优化
VOD_ENABLE_PRELOAD=true           # 启用预加载
VOD_MAX_CONCURRENT=100            # 最大并发点播
VOD_BUFFER_SIZE=5000              # 缓冲大小(ms)
VOD_SOURCE_CHECK_TIMEOUT=3000      # 源检查超时(ms)
VOD_CACHE_DURATION=30             # 源缓存时间(s)

# ZLM 配置
MEDIA_SERVER_HTTP_PORT=8880       # HTTP 端口
MEDIA_SERVER_SECRET=your_secret  # API 密钥

# 录像配置
ZLM_RECORD_FILE_SECOND=300        # 录像分片大小
ZLM_RECORD_SAMPLE_MS=500          # 录像采样间隔

========================================
四、播放协议选择建议
========================================

┌──────────────┬─────────────┬────────────┬───────────────────────┐
│    协议      │   延迟      │   画质     │         适用场景        │
├──────────────┼─────────────┼────────────┼───────────────────────┤
│   MP4 直连   │  低(1-3s)  │   无损     │  本地/内网，高画质点播  │
│   HTTP-FLV   │  中(2-5s)   │   无损     │  通用点播，推荐使用      │
│   HLS        │  高(5-10s) │   可变     │  兼容性最好，所有浏览器  │
│   WebRTC     │  极低(<1s)  │   中等     │  低延迟场景，需要HTTPS  │
└──────────────┴─────────────┴────────────┴───────────────────────┘

推荐优先级：
1. MP4 直连（最快，适用于本地文件）
2. HTTP-FLV（平衡，推荐）
3. HLS（兼容性最好）
4. WebRTC（超低延迟，需要HTTPS）

========================================
五、故障排查清单
========================================

1. 播放卡顿/频繁缓冲
   - 检查网络带宽
   - 调大 maxBufferTime
   - 切换到更稳定的源
   - 检查是否存在跨域问题

2. 花屏/马赛克
   - 检查录像原始文件质量
   - 降低码率或切换到 MP4 直连
   - 检查网络丢包率

3. 首帧加载慢
   - 启用预加载
   - 优化服务器响应时间
   - 使用 CDN
   - 开启 fast_start

4. 跨域问题
   - 配置 Nginx CORS
   - 确保 ZLM 配置了跨域

========================================
六、性能监控指标
========================================

关键指标：
- buffer_health: 缓冲健康度 (0-1)
- bitrate_kbps: 当前码率
- fps: 帧率
- dropped_frames: 丢帧数
- quality_score: 综合质量评分 (0-100)

质量等级阈值：
- EXCELLENT (90-100): 极好
- GOOD (70-89): 良好
- FAIR (50-69): 一般
- POOR (30-49): 较差
- BAD (0-29): 很差

自动处理规则：
- 缓冲不足时自动切换到更稳定的源
- 质量下降时自动尝试更高质量的源
- 错误超过阈值时触发重试

========================================
七、快速部署检查清单
========================================

□ 1. ZLMediaKit 已启动且端口可用
□ 2. 录像文件可访问 (检查 /record/ 目录)
□ 3. 跨域配置正确 (CORS)
□ 4. 前端播放器组件已部署
□ 5. 后端 VOD API 正常工作
□ 6. 质量监控系统已启动

验证命令：
```bash
# 检查 ZLM 状态
curl http://127.0.0.1:8880/index/api/getServerConfig

# 检查录像文件
curl -I http://127.0.0.1:8880/record/test.mp4

# 测试 VOD API
curl http://localhost:8000/api/v1/vod/optimized-url/{record_id}
```
"""

# 配置示例
EXAMPLE_ENV = """
# .env 配置示例

# ========== 点播优化 ==========
VOD_ENABLE_PRELOAD=true
VOD_MAX_CONCURRENT=100
VOD_BUFFER_SIZE=5000
VOD_SOURCE_CHECK_TIMEOUT=3000
VOD_CACHE_DURATION=30

# ========== ZLMediaKit ==========
MEDIA_SERVER_HOST=127.0.0.1
MEDIA_SERVER_HTTP_PORT=8880
MEDIA_SERVER_SECRET=your_secret_key_here
MEDIA_SERVER_RTSP_PORT=554
MEDIA_SERVER_RTMP_PORT=1935
MEDIA_SERVER_RTP_PROXY_PORT=10000

# ========== 录像优化 ==========
ZLM_RECORD_FILE_SECOND=300
ZLM_RECORD_SAMPLE_MS=500
ZLM_PROTOCOL_MP4_MAX_SECOND=300
ZLM_STREAM_NONE_READER_DELAY_MS=600000

# ========== CORS ==========
CORS_ORIGINS=*
"""

# 性能调优建议
PERFORMANCE_TIPS = """
========================================
点播性能调优建议
========================================

1. 服务器端优化
----------------
- 使用 SSD 存储录像文件
- 启用 Nginx 静态文件缓存
- 配置 CDN 分发
- 开启 gzip 压缩
- 使用内网传输避免跨运营商

2. 协议选择
-----------
- 高带宽低延迟：MP4 直连
- 平衡场景：HTTP-FLV
- 高兼容性：HLS
- 低延迟：WebRTC (需HTTPS)

3. 缓冲策略
-----------
- 直播回放：min=500ms, max=2000ms
- 普通点播：min=1000ms, max=5000ms
- 低延迟点播：min=200ms, max=1000ms

4. 监控告警
-----------
建议设置以下告警：
- 质量评分 < 50 持续 30 秒
- 缓冲不足次数 > 5 次/分钟
- 错误率 > 5%
"""
