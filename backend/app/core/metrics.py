"""Prometheus metrics for PyGBSentry.

Exposes Prometheus metrics for external monitoring systems (Grafana/Prometheus).
All metrics here must be reconciled with deploy/monitoring/alert_rules.yml.
"""
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest

# Use a custom registry to avoid conflicts with other libraries
registry = CollectorRegistry()

# --- SIP Metrics ---
sip_messages_total = Counter(
    "pygbsentry_sip_messages_total",
    "Total SIP messages received",
    ["method"],
    registry=registry,
)
sip_responses_total = Counter(
    "pygbsentry_sip_responses_total",
    "Total SIP responses sent",
    ["status_code"],
    registry=registry,
)
sip_inflight = Gauge(
    "pygbsentry_sip_inflight",
    "Current number of in-flight SIP requests",
    registry=registry,
)

# --- Device Metrics ---
devices_online = Gauge(
    "pygbsentry_devices_online",
    "Number of online devices",
    registry=registry,
)
channels_online = Gauge(
    "pygbsentry_channels_online",
    "Number of online channels",
    registry=registry,
)

# --- Stream Metrics ---
active_streams = Gauge(
    "pygbsentry_active_streams",
    "Number of active media streams",
    registry=registry,
)
invite_duration_seconds = Histogram(
    "pygbsentry_invite_duration_seconds",
    "INVITE processing duration in seconds",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=registry,
)
# P2-19: 合并冗余别名 — 仅保留 invite_result_total（alert_rules.yml 引用此指标名）
invite_result_total = Counter(
    "pygbsentry_invite_result_total",
    "Total INVITE requests by result",
    ["result"],
    registry=registry,
)

# --- Port Metrics ---
rtp_ports_allocated = Gauge(
    "pygbsentry_rtp_ports_allocated",
    "Number of currently allocated RTP ports",
    registry=registry,
)
rtp_ports_available = Gauge(
    "pygbsentry_rtp_ports_available",
    "Number of available RTP ports",
    registry=registry,
)

# --- SSRC Metrics ---
ssrc_allocated = Gauge(
    "pygbsentry_ssrc_allocated",
    "Number of currently allocated SSRC values",
    registry=registry,
)

# --- Subscription Metrics ---
subscriptions_active = Gauge(
    "pygbsentry_subscriptions_active",
    "Number of active SIP subscriptions",
    ["direction"],
    registry=registry,
)

# --- Health Check Metrics ---
health_check = Gauge(
    "pygbsentry_health_check",
    "Health check status (1=pass, 0=fail)",
    ["check"],
    registry=registry,
)

# --- Circuit Breaker Metrics ---
CIRCUIT_BREAKER_STATE = Gauge(
    "pygbsentry_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["node"],
    registry=registry,
)

CIRCUIT_BREAKER_FAILURES = Counter(
    "pygbsentry_circuit_breaker_failures_total",
    "Total circuit breaker failures",
    ["node"],
    registry=registry,
)

# --- HTTP Request Metrics ---
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=registry,
)


def metrics_response():
    """Generate Prometheus exposition format response."""
    return generate_latest(registry)
