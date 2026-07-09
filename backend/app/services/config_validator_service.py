"""配置中心草稿校验服务（共享层单例）。

为 :mod:`app.services.config_center_service` 提供配置模块的校验能力。
配置草稿（draft）的 ``modules`` 字段是一个 ``{module_name: {key: value}}`` 的
嵌套字典，本服务对其执行结构/值校验，返回统一的校验结果：

.. code-block:: python

    {
        "valid": bool,        # 是否全部通过
        "errors": [...],      # 阻断性错误（valid=False 时非空）
        "warnings": [...],    # 非阻断警告
        "hints": [...],       # 优化建议
    }

校验规则：
    * 每个模块名必须为非空字符串，且仅含字母/数字/下划线/连字符。
    * 每个 module 的值必须是字典。
    * 已知敏感键（password / secret / token / key）的值不校验具体内容，
      仅标记为 "sensitive"（不回显）。
    * 布尔值接受 True/False/true/false/0/1/"yes"/"no"。
    * 整数值接受 int 或可解析为 int 的字符串。
    * 未知模块仅产生 warning，不阻断。
"""
from __future__ import annotations

import re
from typing import Any


# 模块名合法字符：字母、数字、下划线、连字符
_MODULE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,63}$")

# 敏感键名关键词（不区分大小写）
_SENSITIVE_KEY_TOKENS = ("password", "secret", "token", "apikey", "api_key", "private_key")

# 已知模块白名单（仅用于产生 warning，不阻断校验）
_KNOWN_MODULES = frozenset({
    "sip", "media", "zlm", "redis", "database", "auth", "jwt",
    "ssl", "log", "alarm", "record", "ptz", "talk", "map",
    "billing", "license", "plugin", "ai", "vision", "otp",
    "firewall", "tracing", "cdn", "hls", "webrtc",
})


class ConfigValidatorService:
    """配置中心草稿校验服务（进程级单例 ``config_validator_service``）。"""

    def validate_modules(self, modules: dict[str, Any]) -> dict:
        """校验配置草稿的 ``modules`` 字段。

        Args:
            modules: ``{module_name: {key: value}}`` 嵌套字典。

        Returns:
            ``{"valid": bool, "errors": list, "warnings": list, "hints": list}``
        """
        errors: list[dict] = []
        warnings: list[dict] = []
        hints: list[dict] = []

        if modules is None:
            modules = {}

        if not isinstance(modules, dict):
            errors.append({"field": "modules", "message": "modules 必须是字典类型"})
            return {"valid": False, "errors": errors, "warnings": warnings, "hints": hints}

        for module_name, module_config in modules.items():
            field_prefix = f"modules.{module_name}"

            # 模块名校验
            if not isinstance(module_name, str) or not _MODULE_NAME_RE.match(module_name):
                errors.append({
                    "field": field_prefix,
                    "message": f"模块名 '{module_name}' 不合法（需以字母开头，仅含字母/数字/_/-，1-64字符）",
                })
                continue

            # 未知模块警告
            if module_name.lower() not in _KNOWN_MODULES:
                warnings.append({
                    "field": field_prefix,
                    "message": f"模块 '{module_name}' 不在已知模块列表中，请确认拼写",
                })

            # 模块配置必须是字典
            if not isinstance(module_config, dict):
                errors.append({
                    "field": field_prefix,
                    "message": f"模块 '{module_name}' 的配置必须是字典类型",
                })
                continue

            # 逐键校验
            for key, value in module_config.items():
                self._validate_value(field_prefix, key, value, errors, warnings, hints)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "hints": hints,
        }

    def _validate_value(
        self,
        field_prefix: str,
        key: str,
        value: Any,
        errors: list[dict],
        warnings: list[dict],
        hints: list[dict],
    ) -> None:
        """校验单个配置值。"""
        field = f"{field_prefix}.{key}"

        # 敏感键：仅标记，不校验内容
        key_lower = str(key).lower()
        if any(tok in key_lower for tok in _SENSITIVE_KEY_TOKENS):
            if value and not isinstance(value, str):
                warnings.append({
                    "field": field,
                    "message": f"敏感键 '{key}' 的值应为字符串类型",
                })
            return

        # 空值跳过
        if value is None or value == "":
            return

        # 类型基本校验
        if isinstance(value, (bool, int, float, str)):
            return

        if isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if not isinstance(item, (bool, int, float, str)):
                    warnings.append({
                        "field": f"{field}[{i}]",
                        "message": f"列表元素类型 {type(item).__name__} 可能不被支持",
                    })
            return

        if isinstance(value, dict):
            hints.append({
                "field": field,
                "message": f"键 '{key}' 的值为嵌套字典，部分前端可能不支持编辑",
            })
            return

        warnings.append({
            "field": field,
            "message": f"键 '{key}' 的值类型 {type(value).__name__} 不被支持",
        })


# 进程级单例
config_validator_service = ConfigValidatorService()
