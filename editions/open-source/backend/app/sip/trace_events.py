SIP_TRACE_CONFIG_KEYS = {
    "enabled_key": "SIP_DEBUG_TRACE_ENABLED",
    "sample_rate_key": "SIP_TRACE_SAMPLE_RATE",
}

SIP_TRACE_FIELDS = ["event", "trace_id"]

SIP_TRACE_EVENTS = {
    "handlers": [
        "register_received",
        "register_401_challenge",
        "register_auth_failed",
        "register_ok_platform",
        "register_ok_device",
        "message_received",
        "message_keepalive_platform",
        "message_keepalive_unknown",
        "message_catalog_query_ack",
        "message_catalog_query_push",
        "message_catalog_response",
        "message_record_info",
        "message_alarm",
        "message_mobile_position",
        "message_fallback_200",
        "catalog_push_start",
        "catalog_push_message",
        "device_catalog_retry_initial",
        "device_catalog_retry_attempt",
        "device_catalog_retry_stopped",
        "device_catalog_retry_failed",
        "device_catalog_retry_timeout",
        "device_catalog_retry_success",
        "invite_request_received",
    ],
    "platform_service": [
        "platform_response_received",
        "platform_register_sent",
        "platform_keepalive_sent",
        "platform_keepalive_ack",
        "platform_keepalive_miss_re_register",
        "platform_catalog_sent",
    ],
    "commander": [
        "device_catalog_query_sent",
        "device_mobile_position_subscribe_sent",
        "device_time_sync_sent",
    ],
    "catalog": [
        "catalog_query_sent",
        "deviceinfo_query_sent",
        "devicestatus_query_sent",
    ],
    "ptz": [
        "device_ptz_sent",
        "device_ptz_preset_sent",
    ],
}

SIP_TRACE_EVENT_SET = {
    event
    for events in SIP_TRACE_EVENTS.values()
    for event in events
}

_SIP_TRACE_UNKNOWN_WARNED: set[str] = set()


def is_registered_sip_trace_event(event: str) -> bool:
    return (event or "") in SIP_TRACE_EVENT_SET


def should_warn_unknown_event_once(event: str) -> bool:
    key = (event or "").strip()
    if not key:
        return False
    if key in SIP_TRACE_EVENT_SET:
        return False
    if key in _SIP_TRACE_UNKNOWN_WARNED:
        return False
    _SIP_TRACE_UNKNOWN_WARNED.add(key)
    return True
