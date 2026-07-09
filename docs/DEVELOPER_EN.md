# PyGBSentry Architecture & Development Guide

[中文版](DEVELOPER.md)

> This document is for developers who want to understand PyGBSentry's internal design, extend functionality, or contribute code.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [SIP Stack Deep Dive](#sip-stack-deep-dive)
- [High-Concurrency Optimization](#high-concurrency-optimization)
- [INVITE Full Link](#invite-full-link)
- [Backend Development](#backend-development)
- [Frontend Development](#frontend-development)
- [Plugin Development](#plugin-development)
- [Code Style](#code-style)
- [Testing](#testing)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Client Layer                                  │
│   Web Admin (Vue 3)  │  Mobile App (uni-app)  │  3rd Party/Device   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                        Gateway (Nginx + HTTPS)                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                     Service Layer (FastAPI + asyncio)                │
│   ┌──────────────────────┐  ┌──────────────────────────────────┐   │
│   │   REST API · WebSocket│  │       Plugin Runtime             │   │
│   │   Audit · Config      │  │   Feishu/WeCom/MQTT/S3/AI       │   │
│   └──────────────────────┘  └──────────────────────────────────┘   │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │            Pure Python SIP Signaling Engine                   │  │
│   │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │  │
│   │   │ Sharded  │ │ Object   │ │ Thread   │ │  Handler     │   │  │
│   │   │   Lock   │ │  Pool    │ │  Pool    │ │  Pre-Filter  │   │  │
│   │   │  16x     │ │  2K Pre  │ │ Parallel │ │  70% Less    │   │  │
│   │   └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │  │
│   │   GB28181 Register/Play/Playback/Cascade/PTZ/Alarm/Voice     │  │
│   └──────────────────────────────────────────────────────────────┘  │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │           Streaming Gateway (ZLMediaKit)                       │  │
│   │   WebRTC / FLV / HLS / RTSP / RTMP · RTP Port Pool            │  │
│   └──────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│               Data Layer (PostgreSQL / MySQL / SQLite + Redis)       │
└─────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Choice | Notes |
|:---|:---|:---|
| Backend Framework | FastAPI + uvicorn | Async high-performance web framework |
| Database | PostgreSQL / MySQL / SQLite | SQLite for development |
| Cache | Redis | Sessions, state, rate limiting, distributed locks |
| Streaming | ZLMediaKit | High-performance C++ streaming server |
| Frontend | Vue 3 + Element Plus | Modern responsive UI |
| Mobile | uni-app | Cross-platform (H5/Mini/App) |
| Protocol | GB/T 28181-2022 SIP | Custom pure Python implementation |

### Backend Directory Structure

```
backend/
├── app/
│   ├── api/                    # REST API Routes
│   │   ├── v1/
│   │   │   └── endpoints/     # Business endpoints (devices, streams, alarms, config, etc.)
│   │   └── common/            # Common components (playback, channels, etc.)
│   ├── core/                  # Config, Security, Plugin Manager, Global Singletons
│   │   ├── config.py          # Config center (supports .env hot-reload)
│   │   ├── plugin_manager.py  # Plugin manager
│   │   ├── redis.py           # Redis connection management
│   │   └── ...
│   ├── db/                    # DB sessions, model base, registry
│   ├── models/                # SQLAlchemy ORM models (100+ tables)
│   ├── services/              # Business logic, scheduled tasks
│   │   ├── stream_quality_monitor.py  # 6-dimension stream health scoring
│   │   ├── stream_strategy.py         # Adaptive stream strategy
│   │   ├── qos_monitor.py             # RTCP quality monitoring
│   │   ├── stream_preloader.py        # Predictive preloading
│   │   └── ...
│   ├── sip/                   # ★ Custom SIP/GB28181 Stack Core
│   │   ├── server.py          # SIP Server (UDP/TCP/TLS triple stack)
│   │   ├── dialog_manager.py  # Sharded-Lock Dialog Manager
│   │   ├── transactions.py    # RFC 3261 Full Transaction FSM
│   │   ├── invite.py          # INVITE Session (3300+ lines)
│   │   ├── message.py         # SIP Message Parser + Object Pool
│   │   ├── sdp.py             # SDP Negotiation (GB28181-2022)
│   │   ├── handlers.py        # Signaling handlers (register, heartbeat, catalog, etc.)
│   │   ├── cascade.py         # Platform cascade
│   │   ├── ptz.py             # PTZ control
│   │   ├── auth.py            # Digest authentication
│   │   ├── rtp_port_pool.py   # RTP port pre-allocation pool
│   │   ├── ssrc_manager.py    # SSRC generation & management
│   │   └── ...
│   └── utils/                 # Utility functions
├── alembic/                   # DB migration scripts
├── plugins/                   # Plugin directory + marketplace config
├── scripts/                   # Operations scripts
└── tests/                     # Unit tests + integration tests
```

---

## SIP Stack Deep Dive

### Design Philosophy

PyGBSentry's SIP stack is **built from scratch in pure Python**, with zero C library dependencies (no JAIN-SIP, PJSIP, or eXosip). Design goals:

1. **100% Source Visibility**: Every signaling line is debuggable and modifiable
2. **Full RFC 3261 Compliance**: Transaction FSM, timers, retransmission — complete coverage
3. **Native asyncio**: UDP/TCP dual-stack async I/O based on Python asyncio
4. **Deep GB28181 Integration**: MANSCDP extensions, XML codec, catalog subscription

### Core Modules

#### 1. SIP Server (`server.py`)

```
Data Flow: UDP Datagram → Thread Pool Parse → Task Queue → Worker Pool → Dispatch
```

- **UDP/TCP/TLS Triple Stack**: Simultaneously listens on UDP 5060, TCP 5060, TLS 5061
- **ThreadPoolExecutor Parallel Parse**: SIP parsing in thread pool, never blocks event loop
- **Worker Pool**: asyncio.Queue (10000) + Semaphore (200), controls concurrent processing
- **Overload Protection**: Tiered queue drop (prioritize ACK/BYE/CANCEL), IP rate limiting, register storm protection

Key Code Paths:
- Startup: [`server.py#L215-L270`](backend/app/sip/server.py#L215-L270)
- Message Processing: [`server.py#L144-L161`](backend/app/sip/server.py#L144-L161)
- Overload Protection: [`server.py#L456-L486`](backend/app/sip/server.py#L456-L486)

#### 2. Transaction FSM (`transactions.py`)

Full RFC 3261 transaction state machine implementation:

```
Client INVITE:
  Calling → Proceeding → Completed → Terminated
  (Timer A: Retransmit)  (Timer B: Timeout)  (Timer D: Cleanup)

Server INVITE:
  Proceeding → Completed → Confirmed → Terminated
  (Timer G: 2xx Retransmit)  (Timer H: ACK Wait)  (Timer I: Cleanup)

Non-INVITE:
  Trying → Proceeding → Completed → Terminated
  (Timer E: Retransmit)  (Timer F: Timeout)  (Timer K: Cleanup)
```

Key Code Paths:
- FSM Definition: [`transactions.py#L122-L351`](backend/app/sip/transactions.py#L122-L351)
- Timer G/H/I/J: [`transactions.py#L196-L305`](backend/app/sip/transactions.py#L196-L305)
- RTT-Adaptive T1: [`transactions.py#L25-L55`](backend/app/sip/transactions.py#L25-L55)

#### 3. Dialog Manager (`dialog_manager.py`)

Dialog is the abstraction of end-to-end SIP sessions. Uses **sharded lock** design to avoid contention:

```
Traditional: Single asyncio.Lock guards all Dialogs → high contention at scale
PyGBSentry: 16 shards, Call-ID hash routing → different Dialogs fully parallel

_get_dialog(call_id, from_tag):
    key = f"{call_id}|{from_tag}"
    lock = self._shard_locks[hash(key) % 16]
    async with lock:  # Only locks current shard
        return self._dialogs.get(key)
```

Key Code Paths:
- Shard Lock Init: [`dialog_manager.py#L44-L60`](backend/app/sip/dialog_manager.py#L44-L60)
- Shard Get: [`dialog_manager.py#L62-L63`](backend/app/sip/dialog_manager.py#L62-L63)

#### 4. SIP Message Parsing (`message.py`)

**SipMessage Object Pool** reduces GC pressure:

```python
# Acquire from pool on parse
msg = _msg_pool.acquire()  # 2000 pre-allocated

# Return after processing
SipMessage.release_to_pool(msg)
```

Key Code Paths:
- Object Pool: [`message.py#L390-L424`](backend/app/sip/message.py#L390-L424)
- Parse Entry: [`message.py#L225-L332`](backend/app/sip/message.py#L225-L332)

#### 5. SDP Negotiation (`sdp.py`)

GB/T 28181-2022 SDP negotiation support:

- `a=track` track identifier (precise main/sub stream distinction)
- H.265 fmtp parameters (profile-level-id, sprop-vps, sprop-sps)
- PS/H264/H264S/H265/MPEG4 multi-codec
- SSRC assignment & track association

Key Code Paths:
- H.265 fmtp: [`sdp.py#L265-L266`](backend/app/sip/sdp.py#L265-L266)
- Stream Selection: [`sdp.py#L258-L273`](backend/app/sip/sdp.py#L258-L273)

---

## High-Concurrency Optimization

Four combined optimizations for exceptional Python asyncio performance at scale:

### 1. DialogManager Sharded Lock

| Dimension | Before | After |
|:---|:---|:---|
| Lock Count | 1 `_global_lock` | 16 `_shard_locks` |
| Contention | All operations serial | Different Call-IDs fully parallel |
| Throughput | Single bottleneck | 16x less lock contention |

**Code**: [`dialog_manager.py#L44-L91`](backend/app/sip/dialog_manager.py#L44-L91)

### 2. Handler Pre-Filter

| Dimension | Before | After |
|:---|:---|:---|
| Dispatch | Iterate all handlers | CSeq method exact match |
| Wasted Iteration | Every response iterates all handlers | Only matched handlers called |
| Improvement | — | 70-90% fewer wasted iterations |

**Code**: [`server.py#L152-L175`](backend/app/sip/server.py#L152-L175)

### 3. SipMessage Object Pool

| Dimension | Before | After |
|:---|:---|:---|
| Object Creation | New SipMessage + SipHeaders each time | Reuse from pool |
| GC Pressure | Heavy garbage at 1000 msg/s | 60-80% less GC frequency |
| Pool Size | — | 2000 pre-allocated objects |

**Code**: [`message.py#L390-L424`](backend/app/sip/message.py#L390-L424)

### 4. ThreadPoolExecutor Parallel Parse

| Dimension | Before | After |
|:---|:---|:---|
| Parse Location | Event loop (blocks other coroutines) | Thread pool (multi-core) |
| Thread Count | 0 | CPU cores (max 8) |
| Event Loop | Potentially blocked by parsing | Never blocked |

**Code**: [`server.py#L110-L114`](backend/app/sip/server.py#L110-L114)

---

## INVITE Full Link

INVITE is the most complex signaling flow. From user click to video displayed:

```
User clicks play
    │
    ▼
[1] Generate SSRC (ssrc_manager.py)
    │
    ├──[2] Select ZLM node (media_nodes.py)       ──┐
    ├──[3] Resolve play mode (stream_strategy.py)   ├── 4-Way Parallel
    ├──[4] Load SDP cache (stream_preloader)        ──┤
    ├──[5] Get port from pool (rtp_port_pool)       ──┘
    │
    ▼
[6] Build SDP Offer (sdp.py)
    │
    ▼
[7] Send INVITE (send.py)
    │
    ▼
[8] Transaction FSM (transactions.py)
    ├── Timer A: 500ms retransmit (LAN 50ms)
    ├── 100 Trying received → Stop Timer A
    ├── 200 OK received → Extract SDP Answer
    │
    ▼
[9] Extract remote RTP info
    │
    ▼
[10] Configure ZLM RTP (zlm_rtp_server_service.py)
    │
    ▼
[11] Stream ready, frontend playback
    │
    ▼
[12] Stream Health Monitor (stream_quality_monitor.py)
    ├── Score below threshold → Auto-switch
    └── Normal → Continue monitoring
```

**Key Optimizations**:
- Steps 2-5 run in parallel (`asyncio.gather`), saving 30-50ms
- Step 5 gets port from pre-allocated pool, zero wait
- Step 8 adaptive T1, 50ms on LAN

**Code**:
- 4-Way Parallel: [`invite.py#L2058-L2068`](backend/app/sip/invite.py#L2058-L2068)
- RTP Port Pool: [`rtp_port_pool.py`](backend/app/sip/rtp_port_pool.py)
- Stream Health: [`stream_quality_monitor.py`](backend/app/services/stream_quality_monitor.py)

---

## Backend Development

### Add API Endpoint

1. Create file under `app/api/v1/endpoints/`
2. Define `APIRouter` and handler
3. Register route in `app/api/v1/api.py`

```python
# app/api/v1/endpoints/my_feature.py
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user

router = APIRouter(prefix="/my-feature", tags=["MyFeature"])

@router.get("/")
async def list_items(user=Depends(get_current_user)):
    return {"items": []}
```

### Extend SIP Signaling

1. Register new method handler in `app/sip/handlers.py`
2. Implement handler, return response
3. Extend `transactions.py` for new transaction types if needed

```python
# app/sip/handlers.py
def register_custom_handler():
    sip_server.register_handler("MESSAGE", handle_custom_message)

async def handle_custom_message(msg, addr, proto, transport):
    # Handle custom signaling
    pass
```

### Key Configuration

All config in `backend/.env`, hot-reloadable (some require restart):

| Config | Default | Description |
|:---|:---|:---|
| `SIP_WORKER_CONCURRENCY` | 200 | Worker concurrency |
| `SIP_PARSE_THREADS` | CPU cores | Parse thread count |
| `GLOBAL_DICT_SHARD_COUNT` | 16 | DialogManager shard count |
| `GB28181_VERSION` | 2022 | GB standard version |
| `SIP_T1` | auto | Adaptive (50ms LAN / 500ms WAN) |

---

## Frontend Development

### Tech Stack

- Vue 3 + TypeScript
- Element Plus UI Framework
- Pinia State Management
- Vite Build Tool

### Directory Structure

```
frontend/
├── src/
│   ├── api/           # API request wrappers
│   ├── components/    # Common components
│   ├── views/         # Page components
│   ├── router/        # Route config
│   ├── stores/        # Pinia stores
│   └── utils/         # Utilities
└── dist/              # Build output
```

---

## Plugin Development

See [PLUGIN_SPEC.md](PLUGIN_SPEC.md).

---

## Code Style

### Python

- Lint with `ruff` (config in `backend/ruff.toml`)
- Type hints with Python 3.10+ syntax
- Async functions with `async/await`

### Frontend

- ESLint + Prettier formatting
- Vue 3 Composition API

---

## Testing

```bash
# Run all tests
cd backend
pytest

# Run specific tests
pytest tests/test_sip_core.py
pytest tests/test_sip_message.py

# Integration tests
pytest tests/integration/
```

---

## Further Reading

| Doc | Description |
|:---|:---|
| [PRODUCT_OSS.md](PRODUCT_OSS.md) | Product Capability Whitepaper |
| [PLUGIN_SPEC.md](PLUGIN_SPEC.md) | Plugin Development Spec |
| [MEDIA_SERVER.md](MEDIA_SERVER.md) | ZLMediaKit Configuration |
| [INSTALL_DEPLOY.md](INSTALL_DEPLOY.md) | Production Deployment Guide |