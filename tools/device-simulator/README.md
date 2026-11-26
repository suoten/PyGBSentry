# PyGBSentry 设备模拟器

**没有摄像头也能跑通 GB28181 全链路。** 一条命令拉起 N 台模拟 IPC/NVR，自动完成
注册、心跳、目录上报；平台点播即出画面（ffmpeg 生成的测试卡视频循环流）。

这改变了国标平台的传统体验路径——从"先买台海康设备"才能开始验证，变为先体验后采购。

## 能力清单

| 能力 | 说明 |
|------|------|
| REGISTER + Digest 认证 | 兼容平台 RFC 2617 实现（qop=auth / 无 qop、MD5 / SHA-256 / MD5-sess） |
| Keepalive 心跳 | SN 毫秒时间戳低位起步，进程重启不回退（兼容平台 SN 单调性校验） |
| Catalog 目录上报 | `SumNum` + `DeviceList@Num` 分片约定，含 PTZType/ParentID/经纬度等字段 |
| DeviceInfo / DeviceStatus | 按国标 A.1 响应格式返回 |
| INVITE 点播 | `y=SSRC` / `f=` 回显；UDP 与 TCP（RFC 4571 帧式）媒体均支持 |
| RTP PS 流 | ffmpeg testsrc2 生成 H.264 PS 流，按包起始码切片、按 fps 节拍实时循环发送 |
| PTZ / 其他控制 | 一律 200 OK（信令链路可验证，动作不模拟） |

## 快速开始（与主平台一起部署）

```bash
# 1. 准备主平台 .env（BACKEND_PUBLIC_HOST 必须是宿主机局域网 IP）
# 2. 一条命令启动 平台 + 模拟器
docker compose -f docker-compose.yml -f docker-compose.simulator.yml up -d device-simulator

# 3. 打开管理后台 http://<宿主机IP>/
#    设备列表中会出现 2 台"模拟 NVR"（34020000001310000001 / ...002）
#    点击任意通道"播放"即可看到测试卡画面
```

默认参数下会注册 **2 台设备、每台 2 通道**，设备号 `34020000001310000001` 起
连续编号，通道号类型码为 132（`34020000001320000001` 起全局唯一递增）。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SIM_PLATFORM_HOST` | `backend` | 平台 SIP 地址（compose 网络内直连服务名） |
| `SIM_PLATFORM_PORT` | `5060` | 平台 SIP 端口 |
| `SIM_SERVER_ID` | `34020000002000000001` | 平台 SIP 服务器 ID（须与后台一致） |
| `SIM_SIP_DOMAIN` | `340200` | SIP 域 |
| `SIM_DEVICE_PASSWORD` | `12345678` | 设备密码（须与平台 `SIP_DEFAULT_PASSWORD` 一致） |
| `SIM_DEVICE_COUNT` | `2` | 模拟设备台数 |
| `SIM_CHANNELS_PER_DEVICE` | `2` | 每台通道数 |
| `SIM_KEEPALIVE_INTERVAL` | `60` | 心跳间隔（秒） |
| `SIM_MEDIA_FPS` | `25` | 测试流帧率 |
| `SIM_MEDIA_DURATION` | `30` | PS 片源时长（循环播放） |

自定义示例（模拟 20 台设备、每台 8 通道）：

```bash
SIM_DEVICE_COUNT=20 SIM_CHANNELS_PER_DEVICE=8 \
docker compose -f docker-compose.yml -f docker-compose.simulator.yml up -d device-simulator
```

## 端口与网络说明

- **SIP**：模拟器主动向平台 `5060/udp` 注册（出站连接，无需额外映射）。
- **UDP 媒体（默认）**：模拟器按 INVITE SDP 中的地址发 RTP，即
  `BACKEND_PUBLIC_HOST:30000-30999`（主 compose 已映射），出站即可达。
- **TCP 媒体**：
  - 平台 `setup:passive`（常见，ZLM 监听）→ 模拟器主动连接平台收流端口，无需映射；
  - 平台 `setup:active` → 模拟器在容器内 `42001` 起监听（每台 +10），
    overlay 已映射 `42001-42200`。
- 模拟器接入 `frontend` 网络，与 backend 容器互通。

## 独立运行（不部署平台，用于对接其他国标平台做兼容测试）

```bash
cd tools/device-simulator
pip install nothing  # 零第三方依赖，仅需 ffmpeg 在 PATH 中
python device_simulator.py --platform <平台IP>:5060 \
    --server-id 34020000002000000001 --password 12345678 --count 2
```

## 本地端到端自测（无需 ffmpeg / docker / 真平台）

```bash
python local_e2e_test.py
# PASS 1/4 REGISTER + Digest 认证（服务端独立验算通过）
# PASS 2/4 Catalog 响应（SN 回显 / SumNum / DeviceList@Num / Item 字段齐全）
# PASS 3/4 INVITE/ACK/RTP（收到 10 包，SSRC/PT/marker 正确）
# PASS 4/4 BYE 停流
```

测试内置一个"假平台"，按真实协议顺序驱动模拟器并独立验算 Digest 响应值，
可纳入 CI 作为回归测试。

## Docker Desktop 演示环境注意事项（实测踩坑记录）

本项目 `docker-compose.simulator.yml` 还包含一个 **ZLMediaKit sidecar**（`zlm` 服务，
开源版 backend 镜像不打包 ZLM 二进制）：

- zlm 与 backend 通过 `network_mode: "service:backend"` 共享网络栈，复用主 compose
  已映射的宿主机端口（8880/554/1935/30000-30999），Hook 回调走 `127.0.0.1:8000`；
- **backend 每次重启后必须重启 zlm**（Docker 的 service 网络模式在 backend 重启后
  不会自动重挂 netns）：`docker restart pygbsentry-zlm`；
- **UDP hairpin 不可靠**：容器经宿主机 IP（BACKEND_PUBLIC_HOST）回环发 RTP 在
  Docker Desktop 上经常丢包。已实测解法：把媒体节点的 SDP IP 改为 backend 容器
  在 frontend 网络的 IP，让模拟器容器直连 ZLM：
  ```bash
  # 查 backend 容器 IP（frontend 网络），然后在数据库中设置（或管理后台编辑节点）
  docker inspect pygbsentry-backend-1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}'
  docker exec pygbsentry-db-1 psql -U postgres -d pygb28181 \
    -c "UPDATE media_nodes SET sdp_ip='<backend容器IP>', stream_ip='<backend容器IP>';"
  ```
  容器重建后 IP 会变，需重新设置（管理后台的媒体节点编辑界面可持久化修改）；
- 平台 `APP_ENV=prod` 会拒绝默认弱口令（`SIP_DEFAULT_PASSWORD=12345678` 在黑名单），
  `.env` 中必须设置强口令，且与 `SIM_DEVICE_PASSWORD` 一致；
- 平台默认拒绝陌生设备注册（`ENABLE_AUTO_DISCOVERY=false`）。demo 场景在 `.env`
  设 `ENABLE_AUTO_DISCOVERY=true`；生产环境保持关闭并手工添加设备；
- 若设备曾因密码错误被平台自动拉黑，清库后重启 backend：
  ```bash
  docker exec pygbsentry-db-1 psql -U postgres -d pygb28181 -c "DELETE FROM ip_blacklist;"
  docker restart pygbsentry-backend-1 && docker restart pygbsentry-zlm
  ```

## 故障排查

| 现象 | 原因与处理 |
|------|-----------|
| 设备始终离线 | `SIM_SERVER_ID`/`SIM_SIP_DOMAIN` 与平台配置不一致；或 `SIM_DEVICE_PASSWORD` 与平台 `SIP_DEFAULT_PASSWORD` 不一致（模拟器日志会提示 403） |
| SIP 域不对 | 平台 realm 默认取服务器 ID 前 10 位（`34020000002000000001` → `3402000000`），overlay 已按此设置默认值 |
| 设备在线但点播返回"媒体流尚未就绪" | 按"UDP hairpin"一节把节点 sdp_ip 改为 backend 容器 IP；确认 zlm 容器在运行且 backend 重启后重启过 zlm |
| 平台侧日志"rejecting unknown device" | 平台关闭了自动发现：`.env` 设 `ENABLE_AUTO_DISCOVERY=true`，或在后台先添加设备 |
| 平台侧日志"auto-blacklisting" | 设备密码连续错误触发自动拉黑，按上文清理 `ip_blacklist` |
| 注册无响应 | `SIM_PLATFORM_HOST` 指错了；跨机部署时改为平台宿主机 IP |
| 播放无画面但信令正常 | 确认 ZLM 收流端口 `30000-30999/udp` 已映射；查看模拟器日志中"开始发流"后的目标地址 |
| 画面卡顿 | 降低 `SIM_MEDIA_FPS` 或码率；模拟器容器 CPU 限额是否过小 |

## 已知边界（v1）

- SIP 信令仅 UDP（GB28181 设备侧主流模式）；媒体层 UDP/TCP 均支持。
- 未模拟：录像查询（FileList）、语音对讲、广播、移动位置订阅、报警事件。
- PTZ 控制只回 200 OK，不模拟云台动作。
