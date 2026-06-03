"""
Unified error code system for PyGBSentry.

Provides structured error codes and a custom AppException class
that can be used across all API endpoints for consistent error responses.
"""
from enum import Enum


class ErrorCode(str, Enum):
    # General
    INTERNAL_ERROR = "ERR_001"
    VALIDATION_ERROR = "ERR_002"
    NOT_FOUND = "ERR_003"
    UNAUTHORIZED = "ERR_004"
    FORBIDDEN = "ERR_005"
    RATE_LIMITED = "ERR_006"

    # Device
    DEVICE_NOT_FOUND = "ERR_DEV_001"
    DEVICE_OFFLINE = "ERR_DEV_002"
    DEVICE_ALREADY_EXISTS = "ERR_DEV_003"
    DEVICE_REGISTER_FAILED = "ERR_DEV_004"

    # Channel
    CHANNEL_NOT_FOUND = "ERR_CH_001"
    CHANNEL_ID_INVALID = "ERR_CH_002"

    # Stream
    STREAM_PLAY_FAILED = "ERR_STR_001"
    STREAM_NOT_FOUND = "ERR_STR_002"
    STREAM_STOP_FAILED = "ERR_STR_003"

    # Alarm
    ALARM_NOT_FOUND = "ERR_ALM_001"
    ALARM_ACK_FAILED = "ERR_ALM_002"

    # Plugin
    PLUGIN_INSTALL_FAILED = "ERR_PLG_001"
    PLUGIN_NOT_FOUND = "ERR_PLG_002"
    PLUGIN_LICENSE_INVALID = "ERR_PLG_003"

    # Platform (cascade)
    PLATFORM_NOT_FOUND = "ERR_PLT_001"
    PLATFORM_REGISTER_FAILED = "ERR_PLT_002"

    # Record
    RECORD_NOT_FOUND = "ERR_REC_001"
    RECORD_VERIFY_FAILED = "ERR_REC_002"

    # Auth
    AUTH_INVALID_CREDENTIALS = "ERR_AUTH_001"
    AUTH_TOKEN_EXPIRED = "ERR_AUTH_002"
    AUTH_OTP_REQUIRED = "ERR_AUTH_003"
    AUTH_OTP_INVALID = "ERR_AUTH_004"
    AUTH_ACCOUNT_LOCKED = "ERR_AUTH_005"
    AUTH_PASSWORD_TOO_SHORT = "ERR_AUTH_006"
    AUTH_PASSWORD_NO_UPPER = "ERR_AUTH_007"
    AUTH_PASSWORD_NO_LOWER = "ERR_AUTH_008"
    AUTH_PASSWORD_NO_DIGIT = "ERR_AUTH_009"
    AUTH_PASSWORD_NO_SPECIAL = "ERR_AUTH_010"
    AUTH_USERNAME_TOO_SHORT = "ERR_AUTH_011"
    AUTH_PASSWORD_EMPTY = "ERR_AUTH_012"
    AUTH_PASSWORD_SAME_AS_CURRENT = "ERR_AUTH_013"
    AUTH_CURRENT_PASSWORD_WRONG = "ERR_AUTH_014"

    # User
    USER_NOT_FOUND = "ERR_USR_001"
    USER_ALREADY_EXISTS = "ERR_USR_002"
    USER_CANNOT_DELETE_SELF = "ERR_USR_003"
    USER_ROLE_REQUIRED = "ERR_USR_004"
    USER_ROLE_NOT_FOUND = "ERR_USR_005"

    # Role
    ROLE_CODE_EXISTS = "ERR_ROLE_001"
    ROLE_SYSTEM_CANNOT_DELETE = "ERR_ROLE_002"
    ROLE_IN_USE = "ERR_ROLE_003"

    # Config
    CONFIG_DB_SAVED = "ERR_CFG_001"

    # Map
    MAP_DEFAULT_NAME = "ERR_MAP_001"
    MAP_DEVICE_ID_REQUIRED = "ERR_MAP_002"
    MAP_DEVICE_NOT_FOUND = "ERR_MAP_003"
    MAP_DEVICE_NETWORK_MISSING = "ERR_MAP_004"
    MAP_DEVICE_TRANSPORT_UNAVAILABLE = "ERR_MAP_005"
    MAP_COORDINATES_OUT_OF_RANGE = "ERR_MAP_006"
    MAP_CONFIG_NOT_FOUND = "ERR_MAP_007"

    # Release
    RELEASE_CONFIRM_TOKEN_INVALID = "ERR_REL_001"

    # Integration
    INTG_SOURCE_NOT_SUPPORT_STATE = "ERR_INTG_001"
    INTG_RTMP_NEEDS_EXTERNAL = "ERR_INTG_002"
    INTG_SDK_NEEDS_PLAY_URL = "ERR_INTG_003"
    INTG_FFMPEG_KEY_INVALID = "ERR_INTG_004"
    INTG_FFMPEG_DISABLED = "ERR_INTG_005"
    INTG_SOURCE_NOT_FOUND = "ERR_INTG_006"
    INTG_SAVE_FAILED = "ERR_INTG_007"

    # Work Order
    WO_TITLE_TOO_SHORT = "ERR_WO_001"
    WO_NOT_FOUND = "ERR_WO_002"

    # VOD
    VOD_NOT_FOUND = "ERR_VOD_001"
    VOD_NO_PERMISSION = "ERR_VOD_002"
    VOD_NO_SOURCE = "ERR_VOD_003"

    # Plugin Install
    PLUGIN_ZIP_ONLY = "ERR_PLG_004"
    PLUGIN_URL_NOT_ALLOWED = "ERR_PLG_005"
    PLUGIN_DOWNLOAD_FAILED = "ERR_PLG_006"
    PLUGIN_INSTALL_FAILED_DETAIL = "ERR_PLG_007"
    PLUGIN_NOT_INSTALLED = "ERR_PLG_008"

    # Route Stub
    STUB_NOT_IMPLEMENTED = "ERR_STUB_001"

    # Log
    LOG_ACCESS_DENIED = "ERR_LOG_001"
    LOG_FILE_NOT_FOUND = "ERR_LOG_002"

    # Control
    CONTROL_CRUISE_ID_RANGE = "ERR_CTRL_001"
    CONTROL_PRESET_ID_RANGE = "ERR_CTRL_002"

    # General i18n
    SERVICE_UNAVAILABLE = "ERR_SVC_001"
    PERMISSION_DENIED = "ERR_SVC_002"


class AppException(Exception):
    """Structured application exception with error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        detail: dict | None = None,
        status_code: int = 400,
    ):
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "detail": self.detail,
        }
