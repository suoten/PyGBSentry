import importlib

_LOADED = False

_MODEL_MODULES = [
    "app.models.user",
    "app.models.user_api_key",
    "app.models.asset",
    "app.models.resource",
    "app.models.media_node",
    "app.models.alarm",
    "app.models.platform",
    "app.models.platform_runtime",
    "app.models.record",
    "app.models.stream_session",
    "app.models.device_record_download_task",
    "app.models.map_config",
    "app.models.asset_stream_policy",
    "app.models.asset_stream_health",
    "app.models.alarm_escalation",
    "app.models.alarm_notification",
    "app.models.network_metric",
    "app.models.app_log",
    "app.models.work_order",
    "app.models.billing",
    "app.models.system_setting",
    "app.models.access_source",
    "app.models.push_channel",
    "app.models.sip_trace_event",
    "app.models.device_cluster",
    "app.models.cloud_cluster",
    "app.models.command_session",
    "app.models.command_participant",
    "app.models.command_instruction",
    "app.models.structured_event",
    "app.models.media_port_lease",
    "app.models.device_position",
    "app.models.device_subscription",
    "app.models.ffmpeg_cmd",
    "app.models.rtp_receive_task",
    "app.models.role",
    "app.models.alarm_link_rule",
    "app.models.asset_maintenance",
    "app.models.organization",
    "app.models.region",
    "app.models.platform_catalog_resource",
    "app.models.platform_subscription",
    "app.models.record_schedule",
    "app.models.record_schedule_runtime",
    "app.models.config_draft",
    "app.models.operation_audit",
    "app.models.publish_record",
    "app.models.config_revision",
    "app.models.ip_blacklist",
]


def ensure_model_registry_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    for module_name in _MODEL_MODULES:
        importlib.import_module(module_name)
    _LOADED = True
