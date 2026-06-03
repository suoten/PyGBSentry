# Py-GB28181-Next Technical Specification

## 1. Overview
Py-GB28181-Next is a next-generation video surveillance platform designed to be autonomous, high-performance, and user-friendly. It aims to surpass existing legacy platforms by leveraging a modern tech stack (Python FastAPI + Vue 3), a redesigned database schema for intellectual property autonomy, and embedded media server management for ease of use.

## 2. Architecture

### 2.1 Technology Stack
- **Backend**: Python 3.11+ (FastAPI)
- **Frontend**: Vue 3 (Composition API) + TypeScript + Element Plus + TailwindCSS
- **Database**: PostgreSQL 15+ (Recommended) / MySQL 8.0+
- **Cache**: Redis 7.0+
- **Media Server**: Embedded ZLMediaKit (Managed by Python process)
- **SIP Stack**: Custom AsyncIO-based SIP stack (RFC 3261 compliant)

### 2.2 Core Modules
1.  **SipServer (Core)**: Handles SIP signaling (UDP/TCP 5060), device registration, keep-alive, and catalog synchronization.
2.  **WebAPI**: Provides RESTful APIs for frontend, handles business logic, and manages WebSocket connections.
3.  **MediaManager**: Manages the lifecycle of the embedded ZLMediaKit process, configuration generation, and log aggregation.
4.  **DeviceAdapter**: A plugin-based system to handle vendor-specific (Hikvision, Dahua, Uniview) protocol quirks.
5.  **TaskWorker**: Background tasks for status monitoring, cloud recording management, and alarm processing.

## 3. Key Features

### 3.1 Device Management
- **Standard GB28181**: Support for IPC/NVR registration, heartbeat, and catalog sync.
- **Vendor Compatibility**:
    - **Hikvision Adapter**: Fixes character set issues (GB2312/UTF-8 auto-detection) and catalog XML parsing quirks.
    - **Dahua Adapter**: Maps non-standard PTZ speeds and handles specific alarm formats.
    - **Uniview Adapter**: Handles audio header stripping for G.711 streams.
- **NAT Traversal**: Implementation of `rport` (RFC 3581) for automatic public IP/port detection.

### 3.2 Live Streaming & Playback
- **Low Latency**: WebRTC / FLV / HLS output via ZLMediaKit.
- **Protocol**: TCP (Passive/Active) preference with UDP fallback.
- **Playback**: Seekable recording playback from device SD cards and cloud storage.

### 3.3 Embedded ZLMediaKit
- **Binaries**: Pre-compiled binaries for Windows (x64) and Linux (x64) included in the distribution.
- **Auto-Config**: Python generates `config.ini` based on available ports and user settings at startup.
- **Process Guard**: Automatic restart on crash; log redirection to system logs.

### 3.4 Advanced Features (Commercial Ready)
- **Cascading**: Peer-to-peer cascading support (Upstream & Downstream).
- **GIS Map**: Integration with OpenLayers/Cesium for device positioning and trajectory.
- **Security**: SIP over TLS support (experimental), Operation Auditing (logging every PTZ/Play action).

## 4. System Design

### 4.1 Directory Structure
```text
Py-GB28181-Next/
├── backend/
│   ├── app/
│   │   ├── api/            # REST API endpoints
│   │   ├── core/           # Config, Security, Events
│   │   ├── db/             # Database models & sessions
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   ├── sip/            # SIP Protocol Stack
│   │   └── adapters/       # Vendor Adapters
│   ├── binaries/           # Embedded ZLMediaKit
│   │   ├── win64/
│   │   └── linux64/
│   ├── main.py             # Entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── views/
│   │   └── stores/
│   ├── index.html
│   └── vite.config.ts
├── docs/
└── scripts/
```

### 4.2 API Design (Sample)
- `POST /api/v1/login`: User authentication (JWT).
- `GET /api/v1/devices`: List all devices with status.
- `POST /api/v1/devices/{device_id}/ptz`: Control PTZ.
- `GET /api/v1/streams/play/{device_id}/{channel_id}`: Get playback URL.

## 5. Deployment
- **Docker**: Single container solution including Python backend and ZLMediaKit.
- **Bare Metal**: Python script handles dependency checks and binary execution.
