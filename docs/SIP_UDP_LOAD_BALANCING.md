# SIP UDP 负载均衡部署方案

## 背景

SIP（Session Initiation Protocol）是 GB/T 28181 视频监控系统的核心信令协议，默认基于 **UDP** 传输。与 HTTP/TCP 不同，UDP 是无连接协议，无法直接使用标准的 HTTP/TCP 负载均衡器（如 Nginx upstream、LVS DR 模式等）进行请求分发。这给 SIP 服务的高可用和水平扩展带来了独特挑战。

本文档梳理适用于 PyGBSentry 的 SIP UDP 负载均衡方案，供部署参考。

---

## 方案1：DNS 轮询

**原理**：为 SIP 域名配置多条 A 记录，客户端 DNS 解析时轮询返回不同节点 IP。

**优点**：
- 配置最简单，无需额外组件
- 客户端自动分散到不同节点

**缺点**：
- 无健康检查，故障节点仍会被解析返回
- 无法感知节点负载，分配不均
- DNS 缓存导致切换延迟
- 客户端可能缓存旧解析结果

**适用场景**：开发测试环境，或对可用性要求不高的场景。

**配置示例**：
```
; BIND DNS 配置示例
sip.example.com.  IN  A  10.0.0.1
sip.example.com.  IN  A  10.0.0.2
sip.example.com.  IN  A  10.0.0.3
```

---

## 方案2：HAProxy UDP 负载均衡

**原理**：使用 HAProxy 的 UDP 负载均衡功能，将 SIP 信令分发到后端多个 PyGBSentry 节点。

**优点**：
- 支持健康检查，自动剔除故障节点
- 多种调度算法（轮询、最少连接、哈希等）
- 运维成熟，社区支持好

**缺点**：
- UDP 负载均衡无法维持会话亲和性（SIP 对话需保证同一设备的请求落到同一节点）
- 需要额外部署 HAProxy 实例
- HAProxy 2.4+ 才支持 UDP 负载均衡

**适用场景**：配合 Redis 集群模式使用，HAProxy 仅做信令入口分发。

**配置示例**：
```
# /etc/haproxy/haproxy.cfg
global
    log /dev/log local0

defaults
    timeout connect 5s
    timeout client 30s
    timeout server 30s

frontend sip_udp
    bind *:5060 proto udp
    default_backend sip_servers

backend sip_servers
    balance leastconn
    server node1 10.0.0.1:5060 check
    server node2 10.0.0.2:5060 check
    server node3 10.0.0.3:5060 check
```

> **注意**：HAProxy 的 UDP 健康检查能力有限，建议结合 Redis 集群模式确保会话一致性。

---

## 方案3：Keepalived VIP

**原理**：使用 Keepalived 在多台 PyGBSentry 节点间共享虚拟 IP（VIP），主节点持有 VIP 对外提供服务，主节点故障时 VIP 自动漂移到备节点。

**优点**：
- 配置简单，故障切换自动完成
- 客户端无感知，IP 不变
- 适合主备模式的高可用部署

**缺点**：
- 同一时刻只有一个节点活跃，无法水平扩展
- 脑裂风险（需合理配置仲裁机制）
- 切换期间有短暂中断（通常 1-3 秒）

**适用场景**：小规模部署，主要解决单点故障问题。

**配置示例**：

主节点（10.0.0.1）：
```
# /etc/keepalived/keepalived.conf
vrrp_instance SIP_VIP {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 100
    advert_int 1

    authentication {
        auth_type PASS
        auth_pass PyGBSentry
    }

    virtual_ipaddress {
        10.0.0.100/24
    }

    track_script {
        check_sip
    }
}

vrrp_script check_sip {
    script "/usr/bin/nc -z -u -w2 127.0.0.1 5060"
    interval 3
    fall 2
    rise 1
}
```

备节点（10.0.0.2）：
```
# /etc/keepalived/keepalived.conf
vrrp_instance SIP_VIP {
    state BACKUP
    interface eth0
    virtual_router_id 51
    priority 90
    advert_int 1

    authentication {
        auth_type PASS
        auth_pass PyGBSentry
    }

    virtual_ipaddress {
        10.0.0.100/24
    }

    track_script {
        check_sip
    }
}

vrrp_script check_sip {
    script "/usr/bin/nc -z -u -w2 127.0.0.1 5060"
    interval 3
    fall 2
    rise 1
}
```

---

## 方案4：Redis 集群模式（推荐）

**原理**：PyGBSentry 内置集群支持，通过 Redis 共享 SIP 设备状态，设备按 GB ID 哈希分配到固定节点，确保同一设备的注册、心跳、目录订阅等信令始终由同一节点处理。

**配置方式**：

在 `.env` 或环境变量中设置：
```bash
# 启用 Redis 作为 SIP 状态后端
SIP_STATE_BACKEND=redis

# 启用集群模式
CLUSTER_ENABLED=true

# Redis 连接配置
REDIS_HOST=10.0.0.10
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0

# 集群节点列表（逗号分隔）
CLUSTER_NODES=node1:5060,node2:5060,node3:5060

# 当前节点标识
NODE_ID=node1
```

**优点**：
- 设备按 GB ID 哈希分配，保证会话亲和性
- Redis 共享状态，节点故障时设备可自动重新注册到健康节点
- 支持水平扩展，增加节点即可提升容量
- 无需额外负载均衡器，架构简洁

**缺点**：
- 依赖 Redis，需保证 Redis 高可用
- 节点增减时哈希重分布，部分设备需重新注册
- 需要所有节点能访问同一 Redis 实例

**适用场景**：中大规模生产环境，需要水平扩展和高可用。

**Redis 高可用建议**：
- 使用 Redis Sentinel 或 Redis Cluster 确保 Redis 自身高可用
- 建议至少 3 个 Sentinel 节点
- Redis 持久化开启（AOF + RDB），防止状态丢失

---

## 推荐方案

| 规模 | 推荐方案 | 说明 |
|------|---------|------|
| 小规模（≤200 设备） | Keepalived VIP | 主备模式，配置简单，解决单点故障 |
| 中规模（200-2000 设备） | Redis 集群模式 | 水平扩展，会话亲和，自动故障转移 |
| 大规模（>2000 设备） | Redis 集群模式 + HAProxy | HAProxy 做 UDP 入口分发，Redis 集群保证会话一致性 |

---

## 注意事项

1. **RTP 端口范围**：视频流媒体使用 RTP 协议传输，端口范围通常为 10000-60000（可在 ZLMediaKit 配置中调整）。负载均衡器和防火墙必须开放这些端口，否则视频无法播放。

2. **SIP 会话亲和性**：SIP 是有状态协议，同一设备的 REGISTER、INVITE、BYE 等请求必须由同一节点处理。纯 UDP 负载均衡无法保证这一点，必须配合 Redis 集群模式或基于源 IP 的会话保持。

3. **NAT 穿透**：设备在 NAT 网络下，SIP 信令和 RTP 流的源地址可能与实际地址不同。确保负载均衡器正确处理 NAT 场景，或使用 STUN/TURN 辅助。

4. **时钟同步**：集群节点间必须保持时钟同步（NTP），否则可能导致 SIP 注册超时判断不一致。

5. **防火墙规则**：确保以下端口在节点间和对外均可达：
   - SIP 信令端口（默认 5060 UDP）
   - HTTP API 端口（默认 8080 TCP）
   - RTP 端口范围（默认 10000-60000 UDP）
   - Redis 端口（默认 6379 TCP，仅集群内部）

6. **设备重注册**：节点故障时，分配到该节点的设备需要重新注册。GB/T 28181 设备通常会在注册过期后自动重注册，但可能存在 30-60 秒的切换延迟。
