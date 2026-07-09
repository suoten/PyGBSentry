import sys
import shutil
from pydantic import BaseModel, ConfigDict, field_validator
from app.core.config import settings




class CertbotSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    domain: str = ""
    email: str = ""
    mode: str = "webroot"
    webroot_path: str = "/var/www/certbot"
    renew_threshold_days: int = 30
    renew_check_interval_hours: int = 12
    renew_window_start_hour: int = 2
    renew_window_end_hour: int = 5
    config_dir: str = "/etc/letsencrypt"
    work_dir: str = "/var/lib/letsencrypt"
    logs_dir: str = "/var/log/letsencrypt"
    nginx_reload_cmd: str = "nginx -s reload"
    platform_supported: bool = False
    certbot_available: bool = False

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        if v not in ("webroot", "standalone"):
            raise ValueError(f"mode must be 'webroot' or 'standalone', got '{v}'")
        return v

    @field_validator("renew_threshold_days", "renew_check_interval_hours")
    @classmethod
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError("must be positive")
        return v

    @field_validator("renew_window_start_hour", "renew_window_end_hour")
    @classmethod
    def validate_hour(cls, v):
        if not (0 <= v <= 23):
            raise ValueError("hour must be 0-23")
        return v

    @property
    def cert_live_path(self) -> str:
        return f"{self.config_dir}/live/{self.domain}"

    @property
    def cert_file_path(self) -> str:
        return f"{self.cert_live_path}/fullchain.pem"

    @property
    def key_file_path(self) -> str:
        return f"{self.cert_live_path}/privkey.pem"

    @property
    def is_effective(self) -> bool:
        return self.enabled and self.platform_supported and self.certbot_available and bool(self.domain)


def load_certbot_settings() -> CertbotSettings:
    platform_supported = sys.platform == "linux"
    certbot_available = shutil.which("certbot") is not None
    domain = str(settings.SSL_CERTBOT_DOMAIN or "").strip()
    email = str(settings.SSL_CERTBOT_EMAIL or "").strip()
    if not email and domain:
        email = f"admin@{domain}"
    return CertbotSettings(
        enabled=bool(settings.SSL_CERTBOT_ENABLED),
        domain=domain,
        email=email,
        mode=str(settings.SSL_CERTBOT_MODE or "webroot").strip().lower(),
        webroot_path=str(settings.SSL_CERTBOT_WEBROOT_PATH or "/var/www/certbot").strip(),
        renew_threshold_days=int(settings.SSL_CERTBOT_RENEW_THRESHOLD_DAYS or 30),
        renew_check_interval_hours=int(settings.SSL_CERTBOT_RENEW_CHECK_INTERVAL_HOURS or 12),
        renew_window_start_hour=int(settings.SSL_CERTBOT_RENEW_WINDOW_START_HOUR or 2),
        renew_window_end_hour=int(settings.SSL_CERTBOT_RENEW_WINDOW_END_HOUR or 5),
        config_dir=str(settings.SSL_CERTBOT_CONFIG_DIR or "/etc/letsencrypt").strip(),
        work_dir=str(settings.SSL_CERTBOT_WORK_DIR or "/var/lib/letsencrypt").strip(),
        logs_dir=str(settings.SSL_CERTBOT_LOGS_DIR or "/var/log/letsencrypt").strip(),
        nginx_reload_cmd=str(settings.SSL_CERTBOT_NGINX_RELOAD_CMD or "nginx -s reload").strip(),
        platform_supported=platform_supported,
        certbot_available=certbot_available,
    )
