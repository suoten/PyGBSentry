class ConfigValidatorService:
    def validate_modules(self, modules: dict) -> dict:
        errors: list[dict] = []
        warnings: list[dict] = []
        hints: list[str] = []
        if not isinstance(modules, dict):
            errors.append({"field": "modules", "message": "Config must be an object"})  # i18n
            return {"valid": False, "errors": errors, "warnings": warnings, "hints": hints}
        plugins = modules.get("plugins")
        if isinstance(plugins, dict):
            for plugin_id, plugin_payload in plugins.items():
                if not isinstance(plugin_payload, dict):
                    errors.append({"field": f"plugins.{plugin_id}", "message": "Plugin config must be an object"})  # i18n
                    continue
                enabled = bool(plugin_payload.get("enabled", False))
                webhook_url = plugin_payload.get("webhook_url")
                if enabled and isinstance(webhook_url, str) and webhook_url and not webhook_url.startswith("https://"):
                    errors.append({"field": f"plugins.{plugin_id}.webhook_url", "message": "webhook_url must start with https:// when enabled"})  # i18n
                if plugin_id == "sms_alert" and enabled:
                    api_url = (plugin_payload.get("api_url") or "").strip()
                    phones = (plugin_payload.get("phone_numbers") or "").strip()
                    if not api_url:
                        errors.append({"field": "plugins.sms_alert.api_url", "message": "SMS gateway API URL is required when SMS alert is enabled"})  # i18n
                    if api_url and not api_url.startswith("http://") and not api_url.startswith("https://"):
                        errors.append({"field": "plugins.sms_alert.api_url", "message": "SMS gateway API URL must start with http:// or https://"})  # i18n
                    if not phones:
                        errors.append({"field": "plugins.sms_alert.phone_numbers", "message": "At least one phone number is required when SMS alert is enabled"})  # i18n
                if plugin_id == "tv_wall_suite" and enabled:
                    url = (plugin_payload.get("wall_callback_url") or "").strip()
                    if not url:
                        errors.append({"field": "plugins.tv_wall_suite.wall_callback_url", "message": "TV wall callback URL is required when enabled"})  # i18n
                if plugin_id == "report_suite" and enabled:
                    url = (plugin_payload.get("connector_url") or "").strip()
                    if not url:
                        errors.append({"field": "plugins.report_suite.connector_url", "message": "Report connector URL is required when enabled"})  # i18n
                for rec_plugin, label in (
                    ("face_recognition_suite", "Face Recognition"),
                    ("plate_recognition_suite", "Plate Recognition"),
                    ("behavior_recognition_suite", "Behavior Recognition"),
                ):
                    if plugin_id == rec_plugin and enabled:
                        url = (plugin_payload.get("ai_callback_url") or "").strip()
                        if not url:
                            errors.append({"field": f"plugins.{rec_plugin}.ai_callback_url", "message": f"{label} callback URL is required when enabled"})  # i18n
        stream = modules.get("stream")
        if isinstance(stream, dict):
            pull_timeout = stream.get("pull_timeout")
            if isinstance(pull_timeout, int) and pull_timeout < 8:
                warnings.append({"field": "stream.pull_timeout", "message": "Recommended minimum is 8 seconds"})  # i18n
        if modules.get("alarm") and not modules.get("plugins"):
            hints.append("Consider configuring at least one plugin channel when alarm module is enabled")  # i18n
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings, "hints": hints}


config_validator_service = ConfigValidatorService()
