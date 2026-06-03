"""Backend error message internationalization (zh-CN / en-US)."""
from __future__ import annotations

from app.core.config import settings

_MESSAGES: dict[str, dict[str, str]] = {
    # Auth
    "auth.login_failed": {"zh": "用户名或密码错误", "en": "Invalid username or password"},
    "auth.account_locked": {"zh": "账户已被锁定，请稍后再试", "en": "Account is locked, please try again later"},
    "auth.token_expired": {"zh": "登录已过期，请重新登录", "en": "Session expired, please log in again"},
    "auth.totp_required": {"zh": "需要两步验证", "en": "Two-factor authentication required"},
    "auth.totp_invalid": {"zh": "验证码错误", "en": "Invalid verification code"},
    "auth.api_key_invalid": {"zh": "API密钥无效", "en": "Invalid API key"},
    "auth.api_key_expired": {"zh": "API密钥已过期", "en": "API key has expired"},
    "auth.permission_denied": {"zh": "权限不足", "en": "Permission denied"},
    "auth.role_denied": {"zh": "角色权限不足", "en": "Insufficient role privileges"},

    # Device
    "device.not_found": {"zh": "设备不存在", "en": "Device not found"},
    "device.offline": {"zh": "设备离线", "en": "Device is offline"},
    "device.register_failed": {"zh": "设备注册失败", "en": "Device registration failed"},
    "device.channel_not_found": {"zh": "通道不存在", "en": "Channel not found"},

    # Stream
    "stream.invite_failed": {"zh": "邀请失败", "en": "Invite failed"},
    "stream.invite_timeout": {"zh": "邀请超时", "en": "Invite timeout"},
    "stream.not_ready": {"zh": "流未就绪", "en": "Stream not ready"},
    "stream.ssrc_exhausted": {"zh": "SSRC资源耗尽", "en": "SSRC resource exhausted"},
    "stream.rate_limited": {"zh": "请求过于频繁", "en": "Rate limited"},
    "stream.switch_failed": {"zh": "流切换失败", "en": "Stream switch failed"},

    # Media
    "media.node_unavailable": {"zh": "媒体节点不可用", "en": "Media node unavailable"},
    "media.rtp_port_exhausted": {"zh": "RTP端口耗尽", "en": "RTP ports exhausted"},
    "media.zlm_error": {"zh": "媒体服务器错误", "en": "Media server error"},

    # Record
    "record.not_found": {"zh": "录像不存在", "en": "Recording not found"},
    "record.query_failed": {"zh": "录像查询失败", "en": "Recording query failed"},

    # System
    "system.config_error": {"zh": "配置错误", "en": "Configuration error"},
    "system.db_error": {"zh": "数据库错误", "en": "Database error"},
    "system.redis_error": {"zh": "Redis连接错误", "en": "Redis connection error"},
    "system.internal_error": {"zh": "内部服务器错误", "en": "Internal server error"},
    "system.validation_error": {"zh": "参数验证失败", "en": "Validation error"},
    "system.not_found": {"zh": "资源不存在", "en": "Resource not found"},
    "system.method_not_allowed": {"zh": "方法不允许", "en": "Method not allowed"},
    "system.rate_limited": {"zh": "请求过于频繁", "en": "Too many requests"},

    # Alarm
    "alarm.create_failed": {"zh": "报警创建失败", "en": "Alarm creation failed"},
    "alarm.not_found": {"zh": "报警不存在", "en": "Alarm not found"},
    "alarm.acknowledge_failed": {"zh": "报警确认失败", "en": "Alarm acknowledgement failed"},
    "alarm.query_failed": {"zh": "报警查询失败", "en": "Alarm query failed"},
    "alarm.level_invalid": {"zh": "报警级别无效", "en": "Invalid alarm level"},
    "alarm.type_invalid": {"zh": "报警类型无效", "en": "Invalid alarm type"},
    "alarm.status_invalid": {"zh": "报警状态无效", "en": "Invalid alarm status"},
    "alarm.delete_failed": {"zh": "报警删除失败", "en": "Alarm deletion failed"},

    # Channel
    "channel.not_found": {"zh": "通道不存在", "en": "Channel not found"},
    "channel.create_failed": {"zh": "通道创建失败", "en": "Channel creation failed"},
    "channel.update_failed": {"zh": "通道更新失败", "en": "Channel update failed"},
    "channel.delete_failed": {"zh": "通道删除失败", "en": "Channel deletion failed"},
    "channel.already_exists": {"zh": "通道已存在", "en": "Channel already exists"},
    "channel.stream_busy": {"zh": "通道正在使用中", "en": "Channel stream is busy"},
    "channel.playback_failed": {"zh": "回放失败", "en": "Playback failed"},
    "channel.snapshot_failed": {"zh": "截图失败", "en": "Snapshot failed"},

    # User
    "user.not_found": {"zh": "用户不存在", "en": "User not found"},
    "user.create_failed": {"zh": "用户创建失败", "en": "User creation failed"},
    "user.update_failed": {"zh": "用户更新失败", "en": "User update failed"},
    "user.delete_failed": {"zh": "用户删除失败", "en": "User deletion failed"},
    "user.already_exists": {"zh": "用户已存在", "en": "User already exists"},
    "user.password_mismatch": {"zh": "密码不匹配", "en": "Password mismatch"},
    "user.password_too_weak": {"zh": "密码强度不足", "en": "Password is too weak"},
    "user.cannot_delete_self": {"zh": "不能删除自己", "en": "Cannot delete yourself"},
    "user.last_admin": {"zh": "不能删除最后一个管理员", "en": "Cannot delete the last admin"},

    # Plugin
    "plugin.not_found": {"zh": "插件不存在", "en": "Plugin not found"},
    "plugin.install_failed": {"zh": "插件安装失败", "en": "Plugin installation failed"},
    "plugin.uninstall_failed": {"zh": "插件卸载失败", "en": "Plugin uninstallation failed"},
    "plugin.enable_failed": {"zh": "插件启用失败", "en": "Plugin enable failed"},
    "plugin.disable_failed": {"zh": "插件禁用失败", "en": "Plugin disable failed"},
    "plugin.config_invalid": {"zh": "插件配置无效", "en": "Invalid plugin configuration"},
    "plugin.already_installed": {"zh": "插件已安装", "en": "Plugin already installed"},
    "plugin.license_expired": {"zh": "插件许可证已过期", "en": "Plugin license expired"},
    "plugin.license_invalid": {"zh": "插件许可证无效", "en": "Plugin license invalid"},
    "plugin.dependency_missing": {"zh": "插件依赖缺失", "en": "Plugin dependency missing"},

    # Config
    "config.save_failed": {"zh": "配置保存失败", "en": "Failed to save configuration"},
    "config.load_failed": {"zh": "配置加载失败", "en": "Failed to load configuration"},
    "config.invalid_value": {"zh": "配置值无效", "en": "Invalid configuration value"},
    "config.not_found": {"zh": "配置项不存在", "en": "Configuration item not found"},
    "config.update_conflict": {"zh": "配置更新冲突", "en": "Configuration update conflict"},

    # Billing
    "billing.subscription_expired": {"zh": "订阅已过期", "en": "Subscription has expired"},
    "billing.quota_exceeded": {"zh": "配额已用尽", "en": "Quota exceeded"},
    "billing.payment_failed": {"zh": "支付失败", "en": "Payment failed"},
    "billing.order_not_found": {"zh": "订单不存在", "en": "Order not found"},
    "billing.trial_expired": {"zh": "试用期已结束", "en": "Trial period has ended"},

    # Cascade
    "cascade.connection_failed": {"zh": "级联连接失败", "en": "Cascade connection failed"},
    "cascade.registration_failed": {"zh": "级联注册失败", "en": "Cascade registration failed"},
    "cascade.catalog_sync_failed": {"zh": "目录同步失败", "en": "Catalog sync failed"},
    "cascade.platform_not_found": {"zh": "平台不存在", "en": "Platform not found"},
    "cascade.invite_failed": {"zh": "级联邀请失败", "en": "Cascade invite failed"},

    # Organization
    "organization.not_found": {"zh": "组织不存在", "en": "Organization not found"},
    "organization.name_exists": {"zh": "组织名称已存在", "en": "Organization name already exists"},
    "organization.has_children": {"zh": "组织下有子组织，无法删除", "en": "Cannot delete organization with children"},

    # WorkOrder
    "work_order.not_found": {"zh": "工单不存在", "en": "Work order not found"},
    "work_order.status_invalid": {"zh": "工单状态无效", "en": "Invalid work order status"},
    "work_order.create_failed": {"zh": "工单创建失败", "en": "Failed to create work order"},

    # Map/GIS
    "map.config_not_found": {"zh": "地图配置不存在", "en": "Map configuration not found"},
    "map.provider_invalid": {"zh": "地图服务商无效", "en": "Invalid map provider"},

    # ApiKey
    "api_key.not_found": {"zh": "API密钥不存在", "en": "API key not found"},
    "api_key.revoked": {"zh": "API密钥已吊销", "en": "API key has been revoked"},
    "api_key.scope_insufficient": {"zh": "API密钥权限不足", "en": "Insufficient API key scope"},
}


def _get_lang() -> str:
    """Get current language from settings."""
    lang = getattr(settings, "APP_LANGUAGE", "zh") or "zh"
    return lang if lang in ("zh", "en") else "zh"


def t(key: str, lang: str | None = None, **kwargs) -> str:
    """Translate a message key to the specified or current language.

    Args:
        key: Message key (e.g. "auth.login_failed")
        lang: Language override ('zh' or 'en'). If None, uses settings.APP_LANGUAGE
        **kwargs: Optional format parameters

    Returns:
        Translated string, or the key itself if not found.
    """
    _lang = lang or _get_lang()
    entry = _MESSAGES.get(key)
    if not entry:
        return key
    msg = entry.get(_lang) or entry.get("zh") or key
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, IndexError):
            return msg
    return msg


def t_en(key: str, **kwargs) -> str:
    """Always return English translation (for API responses)."""
    entry = _MESSAGES.get(key)
    if not entry:
        return key
    msg = entry.get("en") or entry.get("zh") or key
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, IndexError):
            return msg
    return msg
