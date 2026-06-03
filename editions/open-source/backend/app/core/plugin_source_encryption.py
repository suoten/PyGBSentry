"""
PyArmor 源码加密检测框架（第5层防护 - 开源版）

开源版不执行加密操作（加密由服务器版完成），但提供：
1. PyArmor CLI 可用性检测
2. 加密插件识别（验证插件是否已被 PyArmor 加密）
3. Cython 原生模块存在性检查

加密流程（完整链路）：
  开发者上传源码 → 服务器版 PyArmor 加密 → 分发加密后代码 → 开源版检测并加载
"""
import logging
import os
import subprocess
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_pyarmor_available() -> bool:
    """检查 PyArmor CLI 是否可用。"""
    try:
        result = subprocess.run(
            ["pyarmor", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def verify_encrypted_plugin(plugin_dir: str) -> dict:
    """
    验证插件目录是否已被 PyArmor 加密。

    参数:
        plugin_dir: 插件目录路径

    返回:
        dict: {"encrypted": bool, "has_runtime": bool, "pyarmor_files": list[str]}
    """
    p = Path(plugin_dir)
    if not p.is_dir():
        return {"encrypted": False, "has_runtime": False, "pyarmor_files": []}

    pyarmor_files = list(p.rglob("pyarmor_runtime*")) + list(p.rglob(".pyarmor*"))
    has_runtime = any(p.rglob("pyarmor_runtime"))
    encrypted = len(pyarmor_files) > 0 or has_runtime
    return {
        "encrypted": encrypted,
        "has_runtime": has_runtime,
        "pyarmor_files": [str(f.relative_to(p)) for f in pyarmor_files[:10]],
    }


def is_cython_native_available() -> bool:
    """检查 Cython 编译的原生验签模块是否可用。"""
    try:
        from app.core._license_native import native_verify_ed25519
        return callable(native_verify_ed25519)
    except ImportError:
        return False


def check_source_encryption_status(plugin_dir: str) -> dict:
    """
    综合检查插件的源码加密状态。

    返回:
        dict: {
            "pyarmor_encrypted": bool,
            "cython_protected": bool,
            "pyarmor_available": bool,
            "encryption_level": str,  # "none" | "pyarmor" | "cython" | "both"
        }
    """
    pyarmor_status = verify_encrypted_plugin(plugin_dir)
    cython_available = is_cython_native_available()
    pyarmor_cli = is_pyarmor_available()

    pyarmor_encrypted = pyarmor_status.get("encrypted", False)

    if pyarmor_encrypted and cython_available:
        level = "both"
    elif pyarmor_encrypted:
        level = "pyarmor"
    elif cython_available:
        level = "cython"
    else:
        level = "none"

    return {
        "pyarmor_encrypted": pyarmor_encrypted,
        "cython_protected": cython_available,
        "pyarmor_available": pyarmor_cli,
        "encryption_level": level,
    }
