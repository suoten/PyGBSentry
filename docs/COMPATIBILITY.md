# 设备兼容性说明

[中文](#) | [English](#english-version)

本文档详细说明 PyGBSentry 系统与各品牌安防设备、平台的兼容性情况。系统基于最新 **GB/T 28181-2022** 标准开发，向下兼容 **GB/T 28181-2016** 设备，理论上任何通过公安部 GB28181 检测的安防设备均可接入。

---

## 目录

- [已验证支持的厂商](#已验证支持的厂商)
- [协议兼容性细节](#协议兼容性细节)
- [常见兼容性问题排查](#常见兼容性问题排查)
- [设备配置建议](#设备配置建议)
- [级联平台兼容性](#级联平台兼容性)
- [相关文档](#相关文档)

---

## 已验证支持的厂商

得益于标准化的协议实现，本系统支持但不限于以下主流厂商的 **NVR**、**IPC** 及 **平台级联**：

### 一线品牌（市场占有率最高的三大厂商）

| 厂商 | 说明 |
|:---|:---|
| **海康威视 (Hikvision)** | IPC、NVR、数字矩阵等全系列产品 |
| **大华股份 (Dahua Technology)** | IPC、NVR、智慧城市产品等 |
| **宇视科技 (Uniview)** | IPC、NVR、平台产品等 |

### 二线品牌与专业领域

| 厂商 | 领域 |
|:---|:---|
| **华为 (Huawei)** | HoloSens 系列、平安城市产品 |
| **英飞拓 (Infinova)** | 安防监控全系列产品 |
| **苏州科达 (Kedacom)** | 视频会议与监控产品 |
| **天地伟业 (Tiandy)** | IPC、NVR、云存储 |
| **中维世纪 (Jovision)** | 中小项目监控产品 |
| **浙江杰峰 (JFtech)** | 安防监控产品 |
| **景阳科技 (Sunell)** | IPC、NVR 产品 |
| **长视科技 (Longse)** | 安防监控产品 |

### AI 与新兴厂商

| 厂商 | 特点 |
|:---|:---|
| **商汤科技 (SenseTime)** | AI 视觉分析 |
| **旷视科技 (Megvii)** | AI 人脸识别 |
| **地平线 (Horizon Robotics)** | AI 芯片与视觉 |
| **格灵深瞳 (DeepGlint)** | AI 行为分析 |
| **瑞为技术 (Reconova)** | 智慧零售与安防 |

### 其他支持厂商

- 深圳市威普莱斯 (WPS)
- 泰和联 (THL)
- 科安讯 (Koanxon)
- 中通服公众信息
- 华荣科技

---

## 协议兼容性细节

### 1. 信令交互 (SIP Signaling)

| 特性 | 说明 |
|:---|:---|
| **RFC 3261 标准** | 严格遵守 SIP 标准状态机，兼容标准 SIP 软终端 |
| **TCP/UDP 自适应** | 同时监听 UDP/5060 和 TCP/5060，自动处理大包导致的 UDP 分片问题（常见于海康/大华高级 NVR） |
| **编码容错** | 自动识别 GB2312、UTF-8、GBK 编码的 XML 报文，解决部分老旧设备乱码问题 |

### 2. 流媒体传输 (Media Transport)

| 特性 | 说明 |
|:---|:---|
| **RTP/PS 解析** | 内置 ZLMediaKit 引擎，拥有业界最强的 PS 流解析能力，能容忍部分设备发出的非标 PS 头 |
| **多路复用** | 支持单端口多路复用，解决 NAT 穿越难题 |
| **H.264/H.265** | 完美支持 H.265 (HEVC) 编码，主流厂商（海康/大华）默认编码格式 |

### 3. 特殊功能适配

| 功能 | 说明 |
|:---|:---|
| **云台控制 (PTZ)** | 实现标准 0xA5 指令集，兼容所有支持 Pelco-D/P 协议的云台 |
| **语音对讲** | 支持 G.711A/U 音频编码 |
| **预置位控制** | 支持预置位查询、调用、巡航轨迹 |

---

## 常见兼容性问题排查

### 问题 1：设备无法注册

**检查项：**

| 检查项 | 说明 |
|:---|:---|
| SIP ID 冲突 | 确保平台 ID 与设备 ID 不重复 |
| 密码错误 | 部分老旧设备仅支持弱密码，本系统支持标准 MD5 Digest 认证 |
| 网络连通性 | 确保 5060 端口可达，UDP 通信正常 |

### 问题 2：视频无法播放

**检查项：**

| 检查项 | 说明 |
|:---|:---|
| 视频编码 | 确保设备输出 H.264 或 H.265 |
| 音频编码 | 建议使用 AAC（Web 播放通常不支持 G.711，ZLM 会尝试转码） |
| 码流参数 | 检查分辨率、帧率、码率是否合理 |

### 问题 3：云台控制无反应

**检查项：**

| 检查项 | 说明 |
|:---|:---|
| 云台协议 | 确认设备支持 Pelco-D 或 Pelco-P 协议 |
| 控制地址 | 确保云台解码器地址与设备配置一致 |
| 透明通道 | 部分设备需要开启透明通道才能转发云台命令 |

### 问题 4：录像回放失败

**检查项：**

| 检查项 | 说明 |
|:---|:---|
| 录像来源 | 确认 NVR/设备已开启录像 |
| 时间同步 | 确保设备与平台时间一致 |
| 录像格式 | 部分设备录像格式不兼容，建议使用国标录像检索 |

---

## 设备配置建议

### 海康威视设备

1. 进入「网络设置 → 高级设置 → 国标」
2. 启用 GB/T 28181
3. 填写平台 ID、SIP 服务器地址、端口
4. 设置认证用户名和密码
5. 选择主码流/子码流

### 大华设备

1. 进入「网络设置 → 平台接入」
2. 启用国标协议
3. 配置服务器地址和设备信息
4. 确保编码格式为 H.264 或 H.265

### 宇视设备

1. 进入「系统管理 → 网络管理 → 国标」
2. 配置平台参数
3. 启用自动注册

---

## 级联平台兼容性

系统支持与以下国标平台级联：

| 平台类型 | 说明 |
|:---|:---|
| 上级平台 | 向上级联注册到公安/政务平台 |
| 平级平台 | 与其他国标平台共享视频资源 |
| 下级平台 | 接收下级设备/平台推送的视频流 |

### 级联配置要点

| 要点 | 说明 |
|:---|:---|
| 平台 ID | 必须唯一，不能与本平台 ID 冲突 |
| 认证方式 | 通常使用 MD5 Digest 认证 |
| 目录订阅 | 建议启用，以便自动同步设备目录 |
| 心跳间隔 | 根据网络环境调整，建议 60 秒 |

---

## 相关文档

| 文档 | 说明 |
|:---|:---|
| [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md) | 部署配置 |
| [MEDIA_SERVER.md](./MEDIA_SERVER.md) | 流媒体配置 |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品能力说明 |

---

# English Version

# Device Compatibility Guide

This document details the compatibility between the PyGBSentry system and various brands of security devices and platforms. The system is built on the latest **GB/T 28181-2022** standard and is backward compatible with **GB/T 28181-2016** devices. In theory, any security device that has passed the Ministry of Public Security's GB28181 inspection can be connected.

---

## Table of Contents

- [Verified Supported Vendors](#verified-supported-vendors)
- [Protocol Compatibility Details](#protocol-compatibility-details)
- [Common Compatibility Troubleshooting](#common-compatibility-troubleshooting)
- [Device Configuration Recommendations](#device-configuration-recommendations)
- [Cascading Platform Compatibility](#cascading-platform-compatibility)
- [Related Documents](#related-documents)

---

## Verified Supported Vendors

Thanks to standardized protocol implementation, this system supports—but is not limited to—the following mainstream vendors for **NVR**, **IPC**, and **platform cascading**:

### Tier-1 Brands (Top three vendors by market share)

| Vendor | Description |
|:---|:---|
| **Hikvision (海康威视)** | Full range of IPC, NVR, and digital matrix products |
| **Dahua Technology (大华股份)** | IPC, NVR, and smart city products |
| **Uniview (宇视科技)** | IPC, NVR, and platform products |

### Tier-2 Brands and Professional Fields

| Vendor | Field |
|:---|:---|
| **Huawei (华为)** | HoloSens series, Safe City products |
| **Infinova (英飞拓)** | Full range of security surveillance products |
| **Kedacom (苏州科达)** | Video conferencing and surveillance products |
| **Tiandy (天地伟业)** | IPC, NVR, and cloud storage |
| **Jovision (中维世纪)** | Small and medium project surveillance products |
| **JFtech (浙江杰峰)** | Security surveillance products |
| **Sunell (景阳科技)** | IPC and NVR products |
| **Longse (长视科技)** | Security surveillance products |

### AI and Emerging Vendors

| Vendor | Features |
|:---|:---|
| **SenseTime (商汤科技)** | AI visual analysis |
| **Megvii (旷视科技)** | AI face recognition |
| **Horizon Robotics (地平线)** | AI chips and vision |
| **DeepGlint (格灵深瞳)** | AI behavior analysis |
| **Reconova (瑞为技术)** | Smart retail and security |

### Other Supported Vendors

- 深圳市威普莱斯 (WPS)
- 泰和联 (THL)
- 科安讯 (Koanxon)
- 中通服公众信息
- 华荣科技

---

## Protocol Compatibility Details

### 1. SIP Signaling

| Feature | Description |
|:---|:---|
| **RFC 3261 Standard** | Strictly follows the SIP standard state machine; compatible with standard SIP soft terminals |
| **TCP/UDP Auto-adaptation** | Listens on both UDP/5060 and TCP/5060; automatically handles UDP fragmentation caused by large packets (common in high-end Hikvision/Dahua NVRs) |
| **Encoding Fault Tolerance** | Automatically recognizes XML messages encoded in GB2312, UTF-8, and GBK, resolving garbled text issues on some older devices |

### 2. Media Transport

| Feature | Description |
|:---|:---|
| **RTP/PS Parsing** | Built-in ZLMediaKit engine with industry-leading PS stream parsing capability; tolerant of non-standard PS headers from some devices |
| **Multiplexing** | Supports single-port multiplexing to solve NAT traversal problems |
| **H.264/H.265** | Full support for H.265 (HEVC) encoding, the default format for mainstream vendors (Hikvision/Dahua) |

### 3. Special Feature Adaptation

| Feature | Description |
|:---|:---|
| **PTZ Control** | Implements the standard 0xA5 instruction set; compatible with all PTZ devices supporting Pelco-D/P protocols |
| **Two-way Audio** | Supports G.711A/U audio encoding |
| **Preset Control** | Supports preset query, recall, and patrol routes |

---

## Common Compatibility Troubleshooting

### Issue 1: Device Cannot Register

**Checklist:**

| Check Item | Description |
|:---|:---|
| SIP ID Conflict | Ensure the platform ID and device ID are not duplicated |
| Password Error | Some older devices only support weak passwords; this system supports standard MD5 Digest authentication |
| Network Connectivity | Ensure port 5060 is reachable and UDP communication is normal |

### Issue 2: Video Cannot Play

**Checklist:**

| Check Item | Description |
|:---|:---|
| Video Encoding | Ensure the device outputs H.264 or H.265 |
| Audio Encoding | AAC is recommended (Web playback usually does not support G.711; ZLM will attempt transcoding) |
| Stream Parameters | Check whether resolution, frame rate, and bit rate are reasonable |

### Issue 3: PTZ Control Has No Response

**Checklist:**

| Check Item | Description |
|:---|:---|
| PTZ Protocol | Confirm the device supports Pelco-D or Pelco-P protocol |
| Control Address | Ensure the PTZ decoder address matches the device configuration |
| Transparent Channel | Some devices require enabling the transparent channel to forward PTZ commands |

### Issue 4: Playback Failure

**Checklist:**

| Check Item | Description |
|:---|:---|
| Recording Source | Confirm that the NVR/device has recording enabled |
| Time Synchronization | Ensure the device time is consistent with the platform time |
| Recording Format | Some device recording formats are incompatible; it is recommended to use national standard (GB) recording search |

---

## Device Configuration Recommendations

### Hikvision Devices

1. Navigate to "Network Settings → Advanced Settings → National Standard (GB)"
2. Enable GB/T 28181
3. Fill in the platform ID, SIP server address, and port
4. Set the authentication username and password
5. Select the main stream/sub stream

### Dahua Devices

1. Navigate to "Network Settings → Platform Access"
2. Enable the national standard protocol
3. Configure the server address and device information
4. Ensure the encoding format is H.264 or H.265

### Uniview Devices

1. Navigate to "System Management → Network Management → National Standard (GB)"
2. Configure platform parameters
3. Enable auto-registration

---

## Cascading Platform Compatibility

The system supports cascading with the following national standard platforms:

| Platform Type | Description |
|:---|:---|
| Upper-level Platform | Register upward to public security/government platforms |
| Peer-level Platform | Share video resources with other GB platforms |
| Lower-level Platform | Receive video streams pushed by lower-level devices/platforms |

### Cascading Configuration Key Points

| Key Point | Description |
|:---|:---|
| Platform ID | Must be unique and must not conflict with the local platform ID |
| Authentication Method | Usually uses MD5 Digest authentication |
| Catalog Subscription | Recommended to enable for automatic device directory synchronization |
| Heartbeat Interval | Adjust according to network conditions; 60 seconds is recommended |

---

## Related Documents

| Document | Description |
|:---|:---|
| [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md) | Deployment configuration |
| [MEDIA_SERVER.md](./MEDIA_SERVER.md) | Media server configuration |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | Product capability description |
