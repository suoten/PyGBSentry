# Implementation Tasks

> 注意：本文档为“实现任务模板/草案”，**不作为**当前仓库真实进度的单一真相源。  
> 开源版的实际执行基线与“已完成/未完成”判定应以对应的产品/工程文档为准（例如 `editions/open-source/docs/` 下的功能状态盘点与实施记录）。  
>
> 保留本文的目的：给“从零搭建 GB28181/媒体服务”的实现路径提供参考，不用于追踪当前版本的落地状态。

## Phase 1: Foundation & Core Infrastructure
- **Project Setup**
    - Initialize Python FastAPI project structure.
    - Initialize Vue 3 + Vite project structure.
    - Set up Docker Compose for DB (PostgreSQL) and Redis.
- **Database Implementation**
    - Implement SQLAlchemy models based on `docs/database_design.md`.
    - Create Alembic migration scripts.
- **Embedded ZLMediaKit Manager**
    - Download/Compile ZLMediaKit binaries for Windows & Linux.
    - Implement `MediaManager` class to detect OS, generate `config.ini`, and spawn process.
    - Implement process monitoring and auto-restart logic.

## Phase 2: SIP Protocol Stack
- **SIP Core**
    - Implement AsyncIO UDP/TCP server for port 5060.
    - Implement SIP message parser (Request/Response).
    - Implement Transaction Layer (Client/Server transactions).
- **GB28181 Signaling**
    - Implement `REGISTER` handler (Authentication, Refresh).
    - Implement `MESSAGE` handler (Keep-alive, Catalog Query).
    - Implement `INVITE` handler (Live Streaming).
    - Implement `BYE` handler (Stop Streaming).

## Phase 3: Media & Device Control
- **Stream Management**
    - Integrate ZLMediaKit WebHook (on_stream_changed, on_play, etc.).
    - Implement dynamic SSRC generation.
    - Implement Stream Proxy logic (RTSP/RTMP -> GB28181).
- **Device Control**
    - Implement PTZ Control API (Pan, Tilt, Zoom).
    - Implement Preset Management (Set/Goto/Del).

## Phase 4: Frontend & UI
- **Basic UI**
    - Login & Dashboard (System Status).
    - Device List & Tree View.
    - Live Preview Player (Integrate Jessibuca/WebRTC).
- **Advanced UI**
    - Split-screen view (1/4/9/16).
    - Cloud Recording Playback timeline.

## Phase 5: Compatibility & Advanced Features
- **Vendor Adapters**
    - Create `BaseAdapter` interface.
    - Implement `HikvisionAdapter` (Charset fix).
    - Implement `DahuaAdapter`.
- **Optimization**
    - Implement NAT Traversal (rport).
    - Optimize TCP Passive mode handling.
