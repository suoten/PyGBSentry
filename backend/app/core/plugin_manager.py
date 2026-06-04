from typing import Any, Callable, Dict, List
import asyncio
import contextlib
import importlib
import inspect
import json
from loguru import logger
import multiprocessing
import os
import math
import pickle
import sys
import threading
import time
from pathlib import Path

import aiohttp
from app.core.config import settings
from app.services.license_service import verify_license_payload
from types import SimpleNamespace


_PLUGIN_SANDBOX_BLOCKED_MODULES: frozenset[str] = frozenset({
    "subprocess", "ctypes", "cffi", "multiprocessing",
    "winreg", "pickle", "shelve", "marshal",
    "socket", "http.client", "urllib", "requests", "httpx",
    "paramiko", "signal", "importlib",
})

_PLUGIN_SANDBOX_BLOCKED_ATTRS: dict[str, frozenset[str]] = {
    "os": frozenset({"system", "popen", "execv", "execve", "spawnl", "spawnle", "spawnv", "spawnve"}),
    "shutil": frozenset({"rmtree"}),
    "sys": frozenset({"exit"}),
}

_PLUGIN_SANDBOX_BLOCKED_BUILTINS: frozenset[str] = frozenset({
    "eval", "exec", "compile", "__import__",
    "open", "globals", "locals", "vars", "dir",
})

_PLUGIN_SANDBOX_BLOCKED_OS_ATTRS: frozenset[str] = frozenset({
    "system", "popen", "remove", "unlink", "rmdir",
    "rename", "replace", "kill", "startfile",
})

# S-06 — 应用源码包根目录，用于校验 app.* 模块是否为真正的内部模块
# 防止插件在 plugins/app/ 下创建模块冒充 app.* 命名空间绕过沙箱
_APP_PKG_ROOT = str(Path(__file__).resolve().parents[1])  # .../backend/app


class _PluginSandboxImportHook:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id

    def find_module(self, fullname, path=None):
        if not bool(getattr(settings, "PLUGIN_SANDBOX_RUNTIME_API_BLOCK_ENABLED", True)):
            return None
        if fullname in _PLUGIN_SANDBOX_BLOCKED_MODULES:
            return self
        return None

    def load_module(self, fullname):
        raise ImportError(
            f"[Sandbox] Plugin '{self.plugin_id}' attempted to import blocked module '{fullname}', "
            f"which is in the dangerous API blacklist and has been blocked by runtime sandbox"  # i18n
        )


def _install_plugin_sandbox_hook(plugin_id: str) -> _PluginSandboxImportHook | None:
    if not bool(getattr(settings, "PLUGIN_SANDBOX_RUNTIME_API_BLOCK_ENABLED", True)):
        return None
    hook = _PluginSandboxImportHook(plugin_id)
    sys.meta_path.insert(0, hook)
    return hook


def _uninstall_plugin_sandbox_hook(hook: _PluginSandboxImportHook | None) -> None:
    if hook and hook in sys.meta_path:
        sys.meta_path.remove(hook)


# P4 死代码 — 删除重复定义（第一个 _install_plugin_sandbox_builtin_guard 已被下面的完整版本替代）

# Standard library / internal modules whose use of exec/eval/compile should never be blocked.
# These modules use these builtins internally (e.g. encodings uses exec when loading codecs).
_INTERNAL_CALLER_PREFIXES: tuple[str, ...] = (
    "encodings.", "importlib.", "_bootstrap.", "_bootstrap_external.",
    "zipimport.", "runpy.", "sqlalchemy.", "alembic.", "pydantic.",
    "starlette.", "uvicorn.", "fastapi.", "anyio.", "httpx.",
    "greenlet.", "asyncio.", "concurrent.", "threading.",
    "loguru.", "uvloop.",
)
# S-06 — 移除 "app." 前缀白名单，改为 _is_internal_caller 中文件路径校验
_INTERNAL_CALLER_EXACT: frozenset[str] = frozenset({
    "encodings", "importlib", "_bootstrap", "_bootstrap_external",
    "zipimport", "runpy", None, "",
    "loguru", "uvloop",
})


def _is_internal_caller(caller: str, frame) -> bool:
    """Check if a caller is an internal (non-plugin) module.
    S-06 — 对 app/app.* 模块增加文件路径校验，
    仅当模块文件位于应用源码目录内才视为内部调用，防止插件通过 app.* 命名空间绕过沙箱"""
    if caller in _INTERNAL_CALLER_EXACT:
        return True
    if any(caller.startswith(p) for p in _INTERNAL_CALLER_PREFIXES):
        return True
    if caller == "app" or caller.startswith("app."):
        mod_file = frame.f_globals.get("__file__", "") if frame else ""
        if mod_file:
            try:
                mod_path = str(Path(mod_file).resolve())
                return mod_path.startswith(_APP_PKG_ROOT)
            except Exception:
                pass
        # 无 __file__ 信息时保守视为内部（如 frozen 模块）
        return True
    return False


def _is_plugin_caller(frame, pid: str) -> bool:
    """Check if the calling chain originates from the plugin (plugin_id or its submodules)."""
    while frame:
        caller = frame.f_globals.get("__name__", "")
        if _is_internal_caller(caller, frame):
            frame = frame.f_back
            continue
        if caller == pid or caller.startswith(pid + "."):
            return True
        return False
    return False


def _is_direct_plugin_caller(frame, pid: str) -> bool:
    """Check if the immediate caller (skipping only stdlib/internal frames) is the plugin.
    Unlike _is_plugin_caller which walks the entire stack, this stops at the first
    non-internal, non-plugin frame, preventing false positives when third-party libs
    (e.g. SQLAlchemy) internally call exec() as part of their normal operation."""
    depth = 0
    while frame and depth < 8:
        caller = frame.f_globals.get("__name__", "")
        if _is_internal_caller(caller, frame):
            frame = frame.f_back
            depth += 1
            continue
        if caller == pid or caller.startswith(pid + "."):
            return True
        return False
    return False

_sandbox_guard_lock = threading.Lock()  # 改为threading.Lock，_load_module是sync函数不能用async with
# FIXED-P0: 模块级 reentrancy 计数器，所有 sandbox guard 共享
# 防止 _guarded 调用 orig() 时 orig 内部又触发其他 guarded builtin 导致无限递归
# 之前每个 _guarded 用独立的 threading.local() 无法感知其他 guard 的递归
_sandbox_reentrancy_depth: int = 0


def _install_plugin_sandbox_builtin_guard(plugin_id: str) -> dict:
    if not bool(getattr(settings, "PLUGIN_SANDBOX_RUNTIME_API_BLOCK_ENABLED", True)):
        return {}
    import builtins as _builtins
    saved = {}
    for name in _PLUGIN_SANDBOX_BLOCKED_BUILTINS:
        original = getattr(_builtins, name, None)
        if original is None or not callable(original):
            continue
        saved[name] = original

        if name == "open":
            def _make_open_guard(orig, pid):
                _inspect_ref = inspect
                def _guarded_open(*args, **kwargs):
                    global _sandbox_reentrancy_depth
                    if _sandbox_reentrancy_depth > 0:
                        return orig(*args, **kwargs)
                    _sandbox_reentrancy_depth += 1
                    try:
                        frame = _inspect_ref.currentframe()
                        if not _is_direct_plugin_caller(frame.f_back, pid):
                            return orig(*args, **kwargs)
                        try:
                            mode = "r"
                            if len(args) > 1:
                                mode = str(args[1])
                            elif "mode" in kwargs:
                                mode = str(kwargs["mode"])
                            # FIXED-P0: 检查原始 mode 中是否包含 "+"（读写模式），
                            # "r+" 允许写入，必须被阻止。之前先 strip "+" 再检查导致 "r+" 绕过。
                            if "+" in mode:
                                raise RuntimeError(
                                    f"[Sandbox] Plugin '{pid}' attempted to call blocked function 'open()' for write operation, "
                                    f"file writing is a dangerous API and has been blocked by runtime sandbox"  # i18n
                                )
                            mode_cleaned = mode.replace("b", "")
                            if mode_cleaned not in ("r",):
                                raise RuntimeError(
                                    f"[Sandbox] Plugin '{pid}' attempted to call blocked function 'open()' for write operation, "
                                    f"file writing is a dangerous API and has been blocked by runtime sandbox"  # i18n
                                )
                            return orig(*args, **kwargs)
                        except RuntimeError:
                            raise
                        except Exception:
                            return orig(*args, **kwargs)
                    finally:
                        _sandbox_reentrancy_depth -= 1
                return _guarded_open

            setattr(_builtins, name, _make_open_guard(original, plugin_id))
            continue

        def _make_guard(orig, blocked_name, pid):
            _inspect_ref = inspect
            def _guarded(*args, **kwargs):
                global _sandbox_reentrancy_depth
                if _sandbox_reentrancy_depth > 0:
                    return orig(*args, **kwargs)
                _sandbox_reentrancy_depth += 1
                try:
                    frame = _inspect_ref.currentframe()
                    plugin_caller = _is_direct_plugin_caller(frame.f_back, pid)
                    if plugin_caller:
                        raise RuntimeError(
                            f"[Sandbox] Plugin '{pid}' attempted to call blocked builtin function '{blocked_name}()', "
                            f"which is in the dangerous API blacklist and has been blocked by runtime sandbox"  # i18n
                        )
                    return orig(*args, **kwargs)
                finally:
                    _sandbox_reentrancy_depth -= 1
            return _guarded

        setattr(_builtins, name, _make_guard(original, name, plugin_id))
    return saved


def _uninstall_plugin_sandbox_builtin_guard(saved: dict) -> None:
    if not saved:
        return
    import builtins as _builtins
    for name, original in saved.items():
        setattr(_builtins, name, original)


def _install_plugin_sandbox_os_attr_guard(plugin_id: str) -> dict:
    if not bool(getattr(settings, "PLUGIN_SANDBOX_RUNTIME_API_BLOCK_ENABLED", True)):
        return {}
    import os as _os
    saved = {}
    for attr_name in _PLUGIN_SANDBOX_BLOCKED_OS_ATTRS:
        original_fn = getattr(_os, attr_name, None)
        if original_fn is None or not callable(original_fn):
            continue
        saved[attr_name] = original_fn

        def _make_guard(orig, name, pid):
            def _guarded_os_fn(*args, **kwargs):
                import inspect as _inspect
                frame = _inspect.currentframe()
                if _is_plugin_caller(frame.f_back, pid):
                    raise RuntimeError(
                        f"[Sandbox] Plugin '{pid}' attempted to call blocked function 'os.{name}()', "
                        f"which is in the dangerous API blacklist and has been blocked by runtime sandbox"  # i18n
                    )
                return orig(*args, **kwargs)
            return _guarded_os_fn

        setattr(_os, attr_name, _make_guard(original_fn, attr_name, plugin_id))
    return saved


def _uninstall_plugin_sandbox_os_attr_guard(saved: dict) -> None:
    if not saved:
        return
    import os as _os
    for attr_name, original_fn in saved.items():
        setattr(_os, attr_name, original_fn)



# -------- Hook process-mode runner (sync callbacks only) --------
def _hook_process_runner(
    module_name: str,
    func_name: str,
    vendor_dir: str | None,
    args: tuple,
    kwargs: dict,
    out_q,
    cpu_timeout_seconds: float | None,
    mem_limit_bytes: int | None,
):
    """
    子进程执行 Hook：用于超时后 terminate。
    - 仅支持 callback 为可通过 module+func_name 重新定位的"模块级函数"
    - args/kwargs 需要可 pickle（外部已做 best-effort 检查）
    - W-13 使用JSON序列化替代pickle传递args/kwargs，防止反序列化漏洞
    """
    try:
        # W-13 使用安全的JSON反序列化替代pickle
        import json as _json
        if isinstance(args, bytes):
            args = _json.loads(args.decode("utf-8"))
        if isinstance(kwargs, bytes):
            kwargs = _json.loads(kwargs.decode("utf-8"))
        if cpu_timeout_seconds and cpu_timeout_seconds > 0:
            try:
                import resource  # type: ignore
                cpu_limit = int(math.ceil(float(cpu_timeout_seconds))) + 1
                if cpu_limit > 0:
                    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
            except Exception as e:
                logger.warning(f"Failed to set CPU limit: {e}")

        if mem_limit_bytes and mem_limit_bytes > 0:
            try:
                import resource  # type: ignore
                resource.setrlimit(resource.RLIMIT_AS, (int(mem_limit_bytes), int(mem_limit_bytes)))
            except Exception as e:
                logger.warning(f"Failed to set memory limit: {e}")

        if vendor_dir:
            try:
                sys.path.insert(0, vendor_dir)
            except Exception as e:
                logger.warning(f"Failed to add vendor dir to path: {e}")

        mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name)
        fn(*args, **kwargs)
        out_q.put({"ok": True})
    except Exception as e:
        out_q.put({"ok": False, "error": str(e)})

# Plugin Hooks
HOOK_ON_STARTUP = "on_startup"
HOOK_ON_SHUTDOWN = "on_shutdown"
HOOK_ON_DEVICE_REGISTER = "on_device_register"
HOOK_ON_DEVICE_OFFLINE = "on_device_offline"
HOOK_ON_STREAM_START = "on_stream_start"
HOOK_ON_STREAM_STOP = "on_stream_stop"
HOOK_ON_ALARM = "on_alarm"
HOOK_ON_MOBILE_POSITION = "on_mobile_position"
HOOK_ON_SIP_RECEIVE = "on_sip_receive"
HOOK_ON_SIP_SEND = "on_sip_send"
HOOK_ALARM_RECORD_LINK = "alarm_record_link"
HOOK_ON_ZLM_STREAM_REG = "ON_ZLM_STREAM_REG"
HOOK_ON_DEVICE_ALARM = "ON_DEVICE_ALARM"
HOOK_ON_UNINSTALL = "on_uninstall"
HOOK_ON_UPGRADE = "on_upgrade"

class PluginManager:
    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Any] = {}
        self.metadata: Dict[str, Dict] = {}
        self.recent_sip_traces = []  # For SIP Trace Visualization
        # Main/Sub 关联：
        # - 在发送 SIP INVITE 时已知 stream_type(main/sub) 和对应的 channel/asset
        # - 在 ZLM on_stream_changed 回调里只拿得到 ssrc，因此用 ssrc 映射回推 main/sub 并补齐上下文
        # 这是内存态缓存，不做持久化。
        self._stream_ctx_by_ssrc: Dict[str, Dict[str, str]] = {}
        self.hooks: Dict[str, List[Callable]] = {
            h: [] for h in [
                HOOK_ON_STARTUP, HOOK_ON_SHUTDOWN, HOOK_ON_UNINSTALL,
                HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE,
                HOOK_ON_STREAM_START, HOOK_ON_STREAM_STOP,
                HOOK_ON_ALARM, HOOK_ON_MOBILE_POSITION, HOOK_ON_SIP_RECEIVE, HOOK_ON_SIP_SEND,
                HOOK_ALARM_RECORD_LINK, HOOK_ON_ZLM_STREAM_REG, HOOK_ON_DEVICE_ALARM, HOOK_ON_UPGRADE,
            ]
        }
        # sys.path 注入 vendor 的运行锁
        # 避免并发 emit 不同插件时，sys.path 的临时修改互相竞争导致 Import 失败。
        self._sys_path_vendor_lock = asyncio.Lock()
        # 用于“安装/卸载插件后后台任务仍在跑”的修复：
        # 记录插件在 HOOK_ON_STARTUP 回调里启动的 asyncio.Task，并在 HOOK_ON_SHUTDOWN 时统一 cancel。
        self._plugin_startup_tasks: set[asyncio.Task] = set()
        self._paid_license_recheck_mono: Dict[str, float] = {}
        self._paid_license_last_ok: Dict[str, bool] = {}
        # T1-02: 在线 license 状态缓存 {plugin_id: {"status": str, "checked_at": float}}
        self._paid_plugin_status_cache: Dict[str, Dict[str, Any]] = {}
        # T1-02: 插件菜单缓存（授权刷新后需失效）
        self._plugin_menu_cache: Dict[str, Any] = {}
        self._plugin_menu_cache_ts: float = 0.0
        # T1-05: OSS 实例注册信息
        self._oss_instance_id: str | None = None
        self._oss_instance_secret: str | None = None
        # G-02/G-08: 插件健康监控 {plugin_id: {"errors": int, "restarts": int, "disabled": bool}}
        self._plugin_health: Dict[str, Dict[str, Any]] = {}
        self._health_check_task: asyncio.Task | None = None

    def _try_load_plugin_json_for_single_file(self, module_name: str) -> dict | None:
        """
        对于 OSS 端的“单文件插件（plugins/*.py）”，运行时本来没有 plugin.json。
        为了让 config_schema/menu 能工作，这里做一个仓库内的兜底：
        - 优先：plugins/{module_name}/plugin.json（如果你安装时以目录方式放置）
        - 其次：editions/server/backend/plugin_packages/{module_name}/plugin.json（仓库内模板）
        """
        try:
            if not module_name:
                return None

            # 1) 本地 plugins/{module_name}/plugin.json
            local_candidate = Path(self.plugin_dir) / module_name / "plugin.json"
            if local_candidate.exists():
                with open(local_candidate, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return meta if isinstance(meta, dict) else None

            # 2) 仓库内 server/backend plugin_packages/{module_name}/plugin.json
            # plugin_manager.py: editions/open-source/backend/app/core/plugin_manager.py
            editions_dir = Path(__file__).resolve().parents[4]  # editions/
            server_candidate = (
                editions_dir / "server" / "backend" / "plugin_packages" / module_name / "plugin.json"
            )
            if server_candidate.exists():
                with open(server_candidate, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return meta if isinstance(meta, dict) else None
        except Exception:
            return None

        return None

    def _reset_runtime(self):
        # S-09 重载前先触发HOOK_ON_SHUTDOWN，让插件优雅关闭资源
        if self.hooks.get(HOOK_ON_SHUTDOWN):
            try:
                shutdown_hooks = self.hooks.get(HOOK_ON_SHUTDOWN, [])
                for cb in list(shutdown_hooks):
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            # R-05 使用get_running_loop()替代get_event_loop()，非异步上下文安全
                            try:
                                loop = asyncio.get_running_loop()
                                loop.create_task(cb())
                            except RuntimeError:
                                logger.warning("No running event loop, skipping async shutdown hook")
                        else:
                            cb()
                    except Exception as e:
                        logger.warning(f"Plugin shutdown hook error during reset: {e}")
            except Exception as e:
                logger.warning(f"Error during plugin shutdown hooks: {e}")
        # Cancel outstanding startup tasks
        for t in list(self._plugin_startup_tasks):
            if not t.done():
                t.cancel()
        self._plugin_startup_tasks.clear()
        self.plugins = {}
        self.metadata = {}
        self._stream_ctx_by_ssrc = {}
        self._paid_license_recheck_mono = {}
        self._paid_license_last_ok = {}
        self.hooks = {
            h: [] for h in [
                HOOK_ON_STARTUP, HOOK_ON_SHUTDOWN, HOOK_ON_UNINSTALL,
                HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE,
                HOOK_ON_STREAM_START, HOOK_ON_STREAM_STOP,
                HOOK_ON_ALARM, HOOK_ON_MOBILE_POSITION, HOOK_ON_SIP_RECEIVE, HOOK_ON_SIP_SEND,
                HOOK_ALARM_RECORD_LINK, HOOK_ON_ZLM_STREAM_REG, HOOK_ON_DEVICE_ALARM, HOOK_ON_UPGRADE,
            ]
        }

    def load_plugins(self):
        """
        Load all plugins from the plugin directory (Supporting subdirectories)
        """
        self._reset_runtime()
        if not os.path.exists(self.plugin_dir):
            os.makedirs(self.plugin_dir)

        if self.plugin_dir not in sys.path:
            sys.path.insert(0, self.plugin_dir)

        # 1. Load Single File Plugins (.py in root)
        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                meta = self._try_load_plugin_json_for_single_file(module_name)
                self._load_module(module_name, meta)

        # 2. Load Package Plugins (Subdirectories with plugin.json)
        for dirname in os.listdir(self.plugin_dir):
            dir_path = os.path.join(self.plugin_dir, dirname)
            if os.path.isdir(dir_path):
                # Check for plugin.json
                json_path = os.path.join(dir_path, "plugin.json")
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r') as f:
                            meta = json.load(f)

                        if meta.get("type") == "paid":
                            if not self._verify_license(dirname, meta, dir_path):
                                logger.warning(f"Skipping paid plugin {dirname}: Invalid license")
                                continue

                        # Import __init__.py or specified entry point
                        # Since dir is in path (via plugin_dir), we import as "dirname"
                        self._load_module(dirname, meta)

                    except Exception as e:
                        logger.error(f"Failed to load plugin package {dirname}: {e}")

    # R-08 插件热更新递归重载子模块，防止新旧代码混合执行
    def _reload_plugin_modules(self, module_name: str):
        """Recursively reload all submodules of a plugin before reloading the main module."""
        prefix = module_name + "."
        mods_to_reload = [k for k in list(sys.modules.keys()) if k.startswith(prefix)]
        for mod_name in sorted(mods_to_reload, key=lambda x: x.count("."), reverse=True):
            if mod_name in sys.modules:
                try:
                    importlib.reload(sys.modules[mod_name])
                except Exception as e:
                    logger.warning(f"Failed to reload submodule {mod_name}: {e}")

    def _load_module(self, module_name, meta=None):
        _was_in_modules = module_name in sys.modules  # W-04 记录导入前状态，失败时清理残留
        try:
            # 合并配置中心已发布的插件配置到 config_template（启动时由 main 注入 _runtime_plugin_config）
            runtime = getattr(self, "_runtime_plugin_config", None) or {}
            saved = runtime.get(module_name) if isinstance(runtime, dict) else None
            if meta and isinstance(saved, dict):
                ct = meta.get("config_template") or {}
                meta = {**meta, "config_template": {**ct, **saved}}
            # If already loaded, reload?
            if module_name in sys.modules:
                self._reload_plugin_modules(module_name)  # R-08 递归重载子模块后再重载主模块
                module = importlib.reload(sys.modules[module_name])
            else:
                # G-15: venv 隔离模式（可选增强）
                venv_enabled = bool(getattr(settings, "PLUGIN_VENV_ISOLATION_ENABLED", False))
                venv_dir_name = str(getattr(settings, "PLUGIN_VENV_DIR_NAME", ".venv") or ".venv")
                venv_dir = os.path.join(self.plugin_dir, str(module_name), venv_dir_name)
                if venv_enabled and os.path.isdir(venv_dir):
                    site_packages = self._find_venv_site_packages(venv_dir)
                    if site_packages and os.path.isdir(site_packages):
                        sys.path.insert(0, site_packages)
                        inserted_venv = True
                    else:
                        inserted_venv = False
                else:
                    inserted_venv = False
                # Allow plugin to vendor dependencies under:
                #   plugins/{plugin_id}/.vendor
                vendor_dir_name = getattr(settings, "PLUGIN_DEPENDENCY_VENDOR_DIR_NAME", ".vendor")
                vendor_dir = os.path.join(self.plugin_dir, str(module_name), str(vendor_dir_name))
                inserted = False
                if vendor_dir and os.path.isdir(vendor_dir):
                    sys.path.insert(0, vendor_dir)
                    inserted = True
                try:
                    with _sandbox_guard_lock:  # 修复async with语法错误（sync函数内不能用async with）+ W-03 加锁保护guard安装/卸载
                        sandbox_hook = _install_plugin_sandbox_hook(module_name)
                        saved_builtins = _install_plugin_sandbox_builtin_guard(module_name)
                        saved_os_attrs = _install_plugin_sandbox_os_attr_guard(module_name)
                        try:
                            module = importlib.import_module(module_name)
                        finally:
                            _uninstall_plugin_sandbox_hook(sandbox_hook)
                            _uninstall_plugin_sandbox_builtin_guard(saved_builtins)
                            _uninstall_plugin_sandbox_os_attr_guard(saved_os_attrs)
                finally:
                    if inserted:
                        with contextlib.suppress(Exception):
                            sys.path.remove(vendor_dir)
                    if inserted_venv and site_packages:
                        with contextlib.suppress(Exception):
                            sys.path.remove(site_packages)

            if hasattr(module, "register"):
                # S-21 热重载前清理旧Hook，防止回调重复执行
                for hook_name, callbacks in self.hooks.items():
                    self.hooks[hook_name] = [
                        cb for cb in callbacks
                        if getattr(cb, "_plugin_id", None) != module_name
                        and (getattr(cb, "__module__", "") or "").split(".", 1)[0].strip() != module_name
                    ]
                logger.info(f"Loading plugin: {module_name}")
                module.register(self)
                self.plugins[module_name] = module
                if meta:
                    self.metadata[module_name] = meta
            else:
                 logger.debug(f"Skipping {module_name}: No 'register' function found.")
        except Exception as e:
            # W-04 清理新导入但加载失败的模块残留，防止下次reload使用损坏的模块对象
            if not _was_in_modules and module_name in sys.modules:
                try:
                    del sys.modules[module_name]
                except Exception:
                    pass
            logger.error(f"Failed to load plugin {module_name}: {e}")

    def _find_venv_site_packages(self, venv_dir: str) -> str | None:
        """G-15: 查找 venv 目录中的 site-packages 路径。"""
        lib_dir = os.path.join(venv_dir, "lib")
        if not os.path.isdir(lib_dir):
            return None
        for python_dir in os.listdir(lib_dir):
            candidate = os.path.join(lib_dir, python_dir, "site-packages")
            if os.path.isdir(candidate):
                return candidate
        return None

    def create_plugin_venv(self, plugin_id: str, requirements_file: str | None = None) -> dict:
        """
        G-15: 为插件创建独立 venv 并安装依赖。
        返回 {"success": bool, "venv_dir": str, "error": str|None}
        """
        import subprocess
        import venv as _venv_mod

        venv_dir_name = str(getattr(settings, "PLUGIN_VENV_DIR_NAME", ".venv") or ".venv")
        venv_dir = os.path.join(self.plugin_dir, str(plugin_id), venv_dir_name)

        try:
            _venv_mod.create(venv_dir, with_pip=True, clear=True)
            pip_path = os.path.join(venv_dir, "bin", "pip") if os.name != "nt" else os.path.join(venv_dir, "Scripts", "pip.exe")
            if not os.path.isfile(pip_path):
                pip_path = os.path.join(venv_dir, "Scripts", "pip.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "pip3")

            if requirements_file and os.path.isfile(requirements_file):
                timeout = int(getattr(settings, "PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS", 300) or 300)
                result = subprocess.run(
                    [pip_path, "install", "-r", requirements_file, "--quiet"],
                    capture_output=True, text=True, timeout=timeout,
                )
                if result.returncode != 0:
                    return {"success": False, "venv_dir": venv_dir, "error": f"pip install failed: {result.stderr[:200]}"}  # i18n

            return {"success": True, "venv_dir": venv_dir, "error": None}
        except subprocess.TimeoutExpired:
            return {"success": False, "venv_dir": venv_dir, "error": "Dependency installation timed out"}  # i18n
        except Exception as e:
            return {"success": False, "venv_dir": venv_dir, "error": str(e)}

    def set_stream_ctx_by_ssrc(
        self,
        ssrc: str,
        *,
        stream_type: str,
        channel_gb_id: str | None = None,
        asset_gb_id: str | None = None,
    ) -> None:
        """
        Cache: ssrc -> {stream_type, channel_gb_id, asset_gb_id}
        """
        if not ssrc:
            return
        st = (stream_type or "").strip().lower()
        normalized = "sub" if st in {"sub", "1"} else "main"
        key = str(ssrc).strip()
        if not key:
            return

        # 简单上限，避免内存无限增长
        if len(self._stream_ctx_by_ssrc) > 10000:
            try:
                first_key = next(iter(self._stream_ctx_by_ssrc.keys()))
                if first_key:
                    self._stream_ctx_by_ssrc.pop(first_key, None)
            except Exception as e:
                logger.warning(f"Failed to pop stream context: {e}")

        ctx: Dict[str, str] = {"sentry_stream_type": normalized}
        if channel_gb_id:
            ctx["sentry_channel_id"] = str(channel_gb_id).strip()
        if asset_gb_id:
            ctx["sentry_asset_gb_id"] = str(asset_gb_id).strip()
        self._stream_ctx_by_ssrc[key] = ctx

    def get_stream_ctx_by_ssrc(self, ssrc: str) -> dict[str, str] | None:
        if not ssrc:
            return None
        key = str(ssrc).strip()
        if not key:
            return None
        return self._stream_ctx_by_ssrc.get(key)

    def pop_stream_ctx_by_ssrc(self, ssrc: str) -> dict[str, str] | None:
        if not ssrc:
            return None
        key = str(ssrc).strip()
        if not key:
            return None
        return self._stream_ctx_by_ssrc.pop(key, None)

    def _verify_license(self, plugin_id: str, meta: dict, plugin_path: str):
        feature_code = str(meta.get("feature_code") or plugin_id)
        tenant_id = str(meta.get("tenant_id") or "default")
        license_path = os.path.join(plugin_path, "license.json")
        license_data = meta.get("license") if isinstance(meta.get("license"), dict) else None
        if not license_data and os.path.exists(license_path):
            try:
                with open(license_path, "r", encoding="utf-8") as f:
                    license_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read license.json for {plugin_id}: {e}")
                return False
        if not license_data:
            logger.error(f"Missing license for paid plugin {plugin_id}")
            return False
        valid, reason = verify_license_payload(
            license_data=license_data,
            tenant_id=tenant_id,
            plugin_id=plugin_id,
            feature_code=feature_code,
        )
        if not valid:
            logger.error(f"Invalid license for paid plugin {plugin_id}: {reason}")
        return valid

    def _paid_plugin_license_currently_valid(self, plugin_id: str, meta: dict) -> bool:
        interval = int(getattr(settings, "PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS", 60) or 0)
        now = time.monotonic()
        pid = str(plugin_id or "").strip()
        if not pid:
            return True
        if interval > 0:
            last_t = self._paid_license_recheck_mono.get(pid)
            if last_t is not None and (now - last_t) < interval:
                return self._paid_license_last_ok.get(pid, True)
        dir_path = os.path.join(self.plugin_dir, pid)
        ok = self._verify_license(pid, meta, dir_path)
        self._paid_license_recheck_mono[pid] = now
        self._paid_license_last_ok[pid] = ok
        if not ok:
            logger.warning(
                "Paid plugin %s hook suspended: license verification failed (will retry per PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS)",  # i18n
                pid,
            )
        return ok

    def _paid_plugin_license_recheck_now(self, plugin_id: str, meta: dict) -> bool:
        """
        强制重验付费插件 license：不受 PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS 的缓存间隔影响。
        """
        pid = str(plugin_id or "").strip()
        if not pid:
            return True
        dir_path = os.path.join(self.plugin_dir, pid)
        ok = self._verify_license(pid, meta, dir_path)
        now = time.monotonic()
        self._paid_license_recheck_mono[pid] = now
        self._paid_license_last_ok[pid] = ok
        if not ok:
            logger.warning(
                "Paid plugin %s hook suspended: license verification failed (background sync triggered recheck)",  # i18n
                pid,
            )
        return ok

    def recheck_paid_plugins_licenses_now(self) -> int:
        """
        遍历 metadata 中已加载的 paid 插件，强制重验并刷新 _paid_license_last_ok。
        返回“尝试重验”的插件数量。
        """
        count = 0
        for pid, meta in list(self.metadata.items()):
            try:
                if str((meta or {}).get("type") or "").lower() != "paid":
                    continue
                count += 1
                self._paid_plugin_license_recheck_now(pid, meta or {})
            except Exception as e:
                logger.error(f"Paid plugin license sync failed: {pid} ({e})")
        return count

    # -------------------------------------------------------------------------
    # T1-02: license 在线状态查询（调用服务器 /license/check-status）
    # -------------------------------------------------------------------------

    async def _check_license_online_status(self, plugin_id: str, meta: dict) -> dict[str, Any]:
        """
        调用服务器 POST /plugins/license/check-status 获取实时授权状态。
        成功时缓存结果，失败时回退到本地验签结果。
        """
        pid = str(plugin_id or "").strip()
        if not pid:
            return {"status": "unknown", "source": "no_plugin_id"}

        base_url = getattr(settings, "PLUGIN_MARKETPLACE_SERVER_URL", None) or ""
        if not base_url:
            base_url = getattr(settings, "PLUGIN_MARKETPLACE_BASE_URL", None) or ""
        if not base_url or not base_url.startswith("http"):
            return {"status": "unknown", "source": "no_server_url"}

        license_data = meta.get("license") if isinstance(meta.get("license"), dict) else None
        if not license_data:
            license_path = os.path.join(self.plugin_dir, pid, "license.json")
            if os.path.exists(license_path):
                try:
                    with open(license_path, "r", encoding="utf-8") as f:
                        license_data = json.load(f)
                except Exception as e:
                    logger.debug(f"check_license_online_status: read license failed {pid}: {e}")
                    return {"status": "unknown", "source": "license_read_failed"}

        if not license_data:
            return {"status": "unknown", "source": "no_license_data"}

        tenant_id = str(meta.get("tenant_id") or "default").strip()
        machine_code = str(meta.get("machine_code") or "").strip() or None

        url = f"{base_url.rstrip('/')}/api/v1/plugins/license/check-status"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json={
                        "plugin_id": pid,
                        "tenant_id": tenant_id,
                        "machine_code": machine_code,
                        "license_data": license_data,
                    },
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        return {"status": "unknown", "source": f"http_{resp.status}"}
                    result = await resp.json()
                    server_status = str(result.get("status") or "unknown")
                    return {
                        "status": server_status,
                        "source": "server",
                        "message": result.get("message", ""),
                        "server_time": result.get("server_time", ""),
                    }
        except asyncio.TimeoutError:
            return {"status": "unknown", "source": "timeout"}
        except Exception as e:
            logger.debug(f"check_license_online_status: request failed {pid}: {e}")
            return {"status": "unknown", "source": f"error_{e.__class__.__name__}"}

    def _paid_plugin_status_cache_get(self, plugin_id: str) -> dict[str, Any] | None:
        """读取缓存，若命中返回状态；过期则返回 None。"""
        cache_ttl = int(getattr(settings, "PLUGIN_PAID_RUNTIME_ONLINE_CHECK_CACHE_SECONDS", 15) or 15)
        entry = self._paid_plugin_status_cache.get(str(plugin_id))
        if not entry:
            return None
        if time.monotonic() - entry.get("_checked_at", 0) > max(cache_ttl, 1):
            return None
        return entry

    def _paid_plugin_status_cache_set(self, plugin_id: str, entry: dict[str, Any]) -> None:
        """写入缓存（含时间戳）。"""
        self._paid_plugin_status_cache[str(plugin_id)] = {
            **entry,
            "_checked_at": time.monotonic(),
        }

    def _invalidate_plugin_menu_cache(self) -> None:
        """清除插件菜单缓存，授权刷新后调用。"""
        self._plugin_menu_cache.clear()
        self._plugin_menu_cache_ts = 0.0
        logger.debug("_invalidate_plugin_menu_cache: menu cache invalidated")  # i18n

    async def _compute_eligible_plugin_ids(self):
        """
        调用 EntitlementEngine.compute_eligible_plugins 计算当前租户的授权并集。
        返回 Set[str]。无 DB 或出错时返回空 set（空 set 表示没有授权，不拦截）。
        """
        from app.services.entitlement_engine import AsyncEntitlementEngine
        from app.db.session import AsyncSessionLocal
        tenant_id = getattr(self, "_tenant_id", None)
        if not tenant_id:
            return set()
        try:
            async with AsyncSessionLocal() as db:
                return await AsyncEntitlementEngine.compute_eligible_plugins(db, tenant_id)
        except Exception:
            logger.warning(
                "EntitlementEngine.compute_eligible_plugins failed for tenant=%s, returning empty set",
                tenant_id,
            )
            return set()

    async def _sync_paid_plugin_online_status(self, plugin_id: str, meta: dict) -> bool:
        """
        T1-02: 查询服务器 license 状态并更新缓存。
        - 返回 True 表示服务器返回 ok（允许使用）
        - 返回 False 表示服务器返回非 ok 或Query failed（降级为本地验签）

        授权刷新时调用 EntitlementEngine.compute_eligible_plugins 做并集计算，
        判断插件是否在 {单品已购} ∪ {套餐内含} 中。
        """
        eligible_ids = await self._compute_eligible_plugin_ids()
        if not eligible_ids:
            # 空 set: EntitlementEngine 不可用或租户无任何授权 → 降级为本地验签
            logger.debug(f"_sync_paid_plugin_online_status: eligible set empty, falling back to local verify for {plugin_id}")
            return False
        if plugin_id not in eligible_ids:
            logger.info(f"_sync_paid_plugin_online_status: plugin {plugin_id} not in eligible set, denied.")
            self._paid_plugin_status_cache_set(plugin_id, {"status": "denied", "source": "entitlement_engine"})
            return False
        pid = str(plugin_id or "").strip()
        if not pid:
            return True

        cached = self._paid_plugin_status_cache_get(pid)
        if cached:
            return cached.get("status") == "ok"

        online_result = await self._check_license_online_status(pid, meta)
        self._paid_plugin_status_cache_set(pid, online_result)

        self._invalidate_plugin_menu_cache()

        if online_result.get("status") == "ok":
            return True
        logger.warning(
            "T1-02: Server returned non-ok license status for %s (%s); falling back to local verify.",
            pid, online_result.get("status")
        )
        return False

    def paid_plugin_online_status_ok(self, plugin_id: str) -> bool:
        """
        同步查询插件在线状态是否 ok。
        - 有缓存且未过期直接返回缓存结果
        - 无缓存或已过期返回本地验签结果（本地验签通过）
        """
        pid = str(plugin_id or "").strip()
        if not pid:
            return True

        cached = self._paid_plugin_status_cache_get(pid)
        if cached and cached.get("source") == "server":
            return cached.get("status") == "ok"

        meta = self.metadata.get(pid)
        if not meta:
            return True
        return self._paid_plugin_license_currently_valid(pid, meta)

    def _hook_emit_allowed(self, hook_name: str, callback: Callable) -> bool:
        if hook_name in (HOOK_ON_STARTUP, HOOK_ON_SHUTDOWN, HOOK_ON_UNINSTALL):
            return True
        pid = getattr(callback, "_plugin_id", None)
        if not pid:
            pid = (getattr(callback, "__module__", "") or "").split(".", 1)[0].strip()
        if not pid or pid not in self.metadata:
            return True
        if not self.is_plugin_healthy(pid):
            return False
        meta = self.metadata.get(pid) or {}
        if str(meta.get("type") or "").lower() != "paid":
            return True
        return self._paid_plugin_license_currently_valid(pid, meta)

    def register_hook(self, hook_name: str, callback: Callable):
        if hook_name in self.hooks:
            # Tag callback with plugin_id so we can inject its vendored deps
            # only while executing this callback (runtime isolation).
            try:
                pid = (getattr(callback, "__module__", "") or "").split(".", 1)[0].strip()
                if pid:
                    setattr(callback, "_plugin_id", pid)
            except Exception as e:
                logger.warning(f"Failed to set plugin ID attribute: {e}")
            self.hooks[hook_name].append(callback)
            logger.debug(f"Registered hook {hook_name} for {callback.__module__}")
        else:
            logger.warning(f"Unknown hook: {hook_name}")

    async def emit(self, hook_name: str, *args, **kwargs):
        """
        触发 Hook；合并 SIP Trace、vendor 隔离、STARTUP 任务追踪与 SHUTDOWN 统一 cancel。
        """
        report: Dict[str, Any] = {
            "hook_name": hook_name,
            "total": 0,
            "executed": 0,
            "success": 0,
            "failed": 0,
            "timeouts": 0,
            "skipped": 0,
            "errors": [],
        }
        if hook_name.upper() == "ON_SIP_SEND" or hook_name.upper() == "ON_SIP_RECV":  # Hook名称大小写不匹配修复，统一转大写比较
            try:
                msg = args[0]
                addr = args[1] if len(args) > 1 else None
                proto = args[2] if len(args) > 2 else "UDP"
                trace = {
                    "time": time.time(),
                    "type": "send" if hook_name == "ON_SIP_SEND" else "recv",
                    "method": getattr(msg, "method", "Response"),
                    "call_id": msg.get_header("Call-ID"),
                    "cseq": msg.get_header("CSeq"),
                    "addr": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                    "proto": proto,
                    "raw": msg.to_bytes().decode("utf-8", errors="ignore"),
                }
                self.recent_sip_traces.append(trace)
                if len(self.recent_sip_traces) > 200:
                    self.recent_sip_traces.pop(0)
            except Exception as e:
                logger.warning(f"Failed to append SIP trace: {e}")

        if hook_name not in self.hooks:
            return report

        callbacks = self.hooks[hook_name]
        if hook_name == HOOK_ON_UNINSTALL:
            target = str(kwargs.get("plugin_id") or "").strip()
            if not target:
                return report
            filtered: List[Callable] = []
            for callback in callbacks:
                pid = getattr(callback, "_plugin_id", None)
                if pid == target:
                    filtered.append(callback)
                    continue
                mod_root = (getattr(callback, "__module__", "") or "").split(".", 1)[0].strip()
                if mod_root == target:
                    filtered.append(callback)
            callbacks = filtered
        report["total"] = len(callbacks)

        timeout_seconds = float(getattr(settings, "PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS", 0) or 0)
        mem_mb = float(getattr(settings, "PLUGIN_SANDBOX_MEMORY_LIMIT_MB", 0) or 0)
        mem_limit_bytes: int | None = None
        if mem_mb and mem_mb > 0:
            mem_limit_bytes = int(mem_mb * 1024 * 1024)

        async def _invoke_one(callback: Callable):
            vendor_dir = None
            inserted = False
            try:
                pid = getattr(callback, "_plugin_id", None) or (getattr(callback, "__module__", "") or "").split(".", 1)[0]
                vendor_dir_name = getattr(settings, "PLUGIN_DEPENDENCY_VENDOR_DIR_NAME", ".vendor")
                if pid:
                    candidate = os.path.join(self.plugin_dir, str(pid), str(vendor_dir_name))
                    if candidate and os.path.isdir(candidate):
                        vendor_dir = candidate
            except Exception:
                vendor_dir = None

            async def _run():
                nonlocal inserted
                if vendor_dir:
                    sys.path.insert(0, vendor_dir)
                    inserted = True
                with _sandbox_guard_lock:  # W-03 emit()中沙箱guard安装/卸载加锁，防止并发修改builtins/os全局状态
                    sandbox_hook = _install_plugin_sandbox_hook(pid)
                    saved_builtins = _install_plugin_sandbox_builtin_guard(pid)
                    saved_os_attrs = _install_plugin_sandbox_os_attr_guard(pid)
                try:
                    if timeout_seconds > 0:
                        if inspect.iscoroutinefunction(callback):
                            await asyncio.wait_for(callback(*args, **kwargs), timeout=timeout_seconds)
                        else:
                            hook_mode = str(getattr(settings, "PLUGIN_HOOK_EXEC_TIMEOUT_MODE", "thread") or "thread").lower()
                            if hook_mode == "process":
                                module_name = getattr(callback, "__module__", None)
                                func_name = getattr(callback, "__name__", None)

                                # 进程模式仅对“模块级函数”可回放；其余情况回退到线程模式
                                if module_name and func_name:
                                    try:
                                        import json as _json
                                        _json.dumps(args)  # W-13 用JSON可序列化检查替代pickle检查
                                        _json.dumps(kwargs)
                                    except Exception:
                                        hook_mode = "thread"
                                    try:
                                        mod = importlib.import_module(str(module_name))
                                        if not hasattr(mod, str(func_name)):
                                            hook_mode = "thread"
                                    except Exception:
                                        hook_mode = "thread"

                                if hook_mode == "process":
                                    def _run_in_subprocess():
                                        import json as _json
                                        ctx = multiprocessing.get_context("spawn")
                                        q = ctx.Queue()
                                        # W-13 使用JSON序列化替代pickle
                                        _json_args = _json.dumps(args).encode("utf-8")
                                        _json_kwargs = _json.dumps(kwargs).encode("utf-8")
                                        p = ctx.Process(
                                            target=_hook_process_runner,
                                            args=(str(module_name), str(func_name), vendor_dir, _json_args, _json_kwargs, q, timeout_seconds, mem_limit_bytes),
                                        )
                                        p.start()
                                        p.join(timeout_seconds)
                                        if p.is_alive():
                                            with contextlib.suppress(Exception):
                                                p.terminate()
                                            with contextlib.suppress(Exception):
                                                p.join()
                                            raise asyncio.TimeoutError()

                                        # 正常结束：读取返回状态
                                        try:
                                            msg = q.get(timeout=0.5)
                                        except Exception:
                                            msg = None
                                        if isinstance(msg, dict) and msg.get("ok") is False:
                                            raise RuntimeError(msg.get("error") or "hook_process_failed")

                                    # 避免 join() 阻塞事件循环
                                    await asyncio.to_thread(_run_in_subprocess)
                                else:
                                    # 回退到线程模式
                                    await asyncio.wait_for(asyncio.to_thread(callback, *args, **kwargs), timeout=timeout_seconds)
                            else:
                                # 同进程“超时隔离”：同步回调放到线程池执行，避免卡死事件循环
                                await asyncio.wait_for(asyncio.to_thread(callback, *args, **kwargs), timeout=timeout_seconds)
                    else:
                        # S-05 sync callbacks always run in thread pool to prevent
                        # blocking the event loop even when timeout_seconds <= 0
                        if inspect.iscoroutinefunction(callback):
                            await callback(*args, **kwargs)
                        else:
                            await asyncio.to_thread(callback, *args, **kwargs)
                except asyncio.TimeoutError:
                    report["timeouts"] += 1
                    report["errors"].append(
                        {
                            "module": getattr(callback, "__module__", "?"),
                            "reason": "timeout",
                        }
                    )
                    logger.warning(
                        "Plugin hook timeout: %s (%s), timeout=%.2fs; skip this callback",
                        hook_name,
                        getattr(callback, "__module__", "?"),
                        timeout_seconds,
                    )
                    # 超时“告警记录”落点：
                    # 触发 HOOK_ON_ALARM 走现有告警插件链路（若配置了告警渠道）。
                    try:
                        if HOOK_ON_ALARM in self.hooks and self.hooks.get(HOOK_ON_ALARM):
                            alarm = SimpleNamespace(
                                alarm_type="plugin_hook_timeout",
                                hook_name=hook_name,
                                plugin_module=getattr(callback, "__module__", None),
                                timeout_seconds=timeout_seconds,
                                time=time.time(),
                                description=f"Plugin hook timeout: {hook_name} ({getattr(callback, '__module__', '?')}); timeout={timeout_seconds:.2f}s",
                            )
                            asyncio.create_task(self.emit(HOOK_ON_ALARM, alarm))
                    except Exception as e:
                        logger.warning(f"Failed to emit alarm for hook timeout: {e}")
                    return
                except Exception as e:
                    report["failed"] += 1
                    report["errors"].append(
                        {
                            "module": getattr(callback, "__module__", "?"),
                            "reason": str(e),
                        }
                    )
                    logger.error(f"Error in plugin hook {hook_name} ({getattr(callback, '__module__', '?')}): {e}")
                    try:
                        err_pid = getattr(callback, "_plugin_id", None) or (getattr(callback, "__module__", "") or "").split(".", 1)[0].strip()
                        if err_pid:
                            self.record_plugin_error(err_pid, str(e))
                    except Exception as e:
                        logger.warning(f"Failed to record plugin error: {e}")
                    return
                else:
                    report["success"] += 1
                    try:
                        ok_pid = getattr(callback, "_plugin_id", None) or (getattr(callback, "__module__", "") or "").split(".", 1)[0].strip()
                        if ok_pid:
                            self.record_plugin_success(ok_pid)
                    except Exception as e:
                        logger.warning(f"Failed to record plugin success: {e}")
                finally:
                    with _sandbox_guard_lock:  # W-03 guard卸载也加锁
                        _uninstall_plugin_sandbox_hook(sandbox_hook)
                        _uninstall_plugin_sandbox_builtin_guard(saved_builtins)
                        _uninstall_plugin_sandbox_os_attr_guard(saved_os_attrs)
                    if inserted and vendor_dir:
                        with contextlib.suppress(Exception):
                            sys.path.remove(vendor_dir)

            if vendor_dir:
                async with self._sys_path_vendor_lock:
                    await _run()
            else:
                await _run()

        for callback in callbacks:
            if not self._hook_emit_allowed(hook_name, callback):
                report["skipped"] += 1
                continue
            report["executed"] += 1
            if hook_name == HOOK_ON_STARTUP:
                before = set(asyncio.all_tasks())
                await _invoke_one(callback)
                after = set(asyncio.all_tasks())
                new_tasks = {
                    t
                    for t in (after - before)
                    if isinstance(t, asyncio.Task) and not t.done()
                }
                self._plugin_startup_tasks.update(new_tasks)
            else:
                await _invoke_one(callback)

        if hook_name == HOOK_ON_SHUTDOWN and self._plugin_startup_tasks:
            for t in list(self._plugin_startup_tasks):
                try:
                    if not t.done():
                        t.cancel()
                except Exception as e:
                    logger.warning(f"Failed to cancel plugin startup task: {e}")
            self._plugin_startup_tasks.clear()
        elif hook_name == HOOK_ON_UNINSTALL:
            # S-03 — 卸载插件时清理所有 startup 后台任务
            # （任务未按插件ID分组，故统一清理；HOOK_ON_SHUTDOWN 路径同理）
            for t in list(self._plugin_startup_tasks):
                try:
                    if not t.done():
                        t.cancel()
                except Exception:
                    pass
            self._plugin_startup_tasks.clear()
        return report

    # -------------------------------------------------------------------------
    # T1-05: OSS 实例注册与 install-check 认证
    # -------------------------------------------------------------------------

    def get_oss_instance_id(self) -> str | None:
        """返回当前已注册的实例 ID。"""
        return self._oss_instance_id

    def get_oss_instance_headers(self, body_bytes: bytes) -> dict:
        """
        返回用于 install-check 请求的认证头。
        计算 HMAC-SHA256(instance_secret, body) 作为签名。
        """
        if not self._oss_instance_id or not self._oss_instance_secret:
            return {}
        import hmac
        sig = hmac.new(
            self._oss_instance_secret.encode(),
            body_bytes,
            "sha256",
        ).hexdigest()
        return {
            "X-Instance-Id": self._oss_instance_id,
            "X-Instance-Signature": sig,
        }

    async def register_oss_instance(self, machine_code: str, description: str | None = None) -> dict:
        """
        向服务器注册 OSS 实例，获取 instance_id 和 instance_secret。
        仅在 PLUGIN_MARKETPLACE_ENABLED=True 时执行，否则静默返回。
        """
        if not bool(getattr(settings, "PLUGIN_MARKETPLACE_ENABLED", False)):
            logger.debug("[OSS-Register] PLUGIN_MARKETPLACE_ENABLED=False, skipping OSS instance registration")
            return {"ok": False, "error": "plugin marketplace disabled"}
        import json as _json
        server_url = getattr(settings, "PLUGIN_MARKETPLACE_SERVER_URL", None) or ""
        if not server_url:
            server_url = getattr(settings, "PLUGIN_MARKETPLACE_BASE_URL", None) or ""
        if not server_url:
            logger.warning("[OSS-Register] PLUGIN_MARKETPLACE_SERVER_URL not configured, skipping instance registration")  # i18n
            return {"ok": False, "error": "server not configured"}

        url = f"{server_url.rstrip('/')}/api/v1/plugins/oss/register"
        payload = {"machine_code": machine_code, "description": description or None}
        body_bytes = _json.dumps(payload).encode("utf-8")

        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, data=body_bytes, headers={
                        "Content-Type": "application/json",
                    }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self._oss_instance_id = data.get("instance_id")
                            self._oss_instance_secret = data.get("instance_secret")
                            logger.info(f"[OSS-Register] Instance registered successfully: {self._oss_instance_id}")  # i18n
                            return {"ok": True, **data}
                        else:
                            text = await resp.text()
                            logger.warning(f"[OSS-Register] Registration failed HTTP {resp.status}: {text[:200]}")  # i18n
                            return {"ok": False, "error": f"HTTP {resp.status}: {text[:200]}"}
            except aiohttp.ClientError as exc:
                logger.warning(f"[OSS-Register] Network error (attempt {attempt + 1}): {exc}")  # i18n
                if attempt == 1:
                    return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": "max retries"}

    async def deregister_oss_instance(self) -> dict:
        """注销 OSS 实例。"""
        import json as _json
        if not self._oss_instance_id:
            return {"ok": False, "error": "not registered"}
        server_url = getattr(settings, "PLUGIN_MARKETPLACE_SERVER_URL", None) or ""
        if not server_url:
            server_url = getattr(settings, "PLUGIN_MARKETPLACE_BASE_URL", None) or ""
        if not server_url:
            return {"ok": False, "error": "server not configured"}

        url = f"{server_url.rstrip('/')}/api/v1/plugins/oss/deregister"
        payload = {"instance_id": self._oss_instance_id}
        body_bytes = _json.dumps(payload).encode("utf-8")
        headers = self.get_oss_instance_headers(body_bytes)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=body_bytes, headers={
                    "Content-Type": "application/json",
                    **headers,
                }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        self._oss_instance_id = None
                        self._oss_instance_secret = None
                        logger.info("[OSS-Register] Instance deregistered successfully")  # i18n
                        return {"ok": True}
                    return {"ok": False, "error": f"HTTP {resp.status}: {text[:200]}"}
        except aiohttp.ClientError as exc:
            return {"ok": False, "error": str(exc)}

    async def oss_instance_check_in(self) -> dict:
        """向服务器发送心跳，保持 OSS 实例活跃状态。"""
        import json as _json
        if not self._oss_instance_id:
            return {"ok": False, "error": "not registered"}
        server_url = getattr(settings, "PLUGIN_MARKETPLACE_SERVER_URL", None) or ""
        if not server_url:
            server_url = getattr(settings, "PLUGIN_MARKETPLACE_BASE_URL", None) or ""
        if not server_url:
            return {"ok": False, "error": "server not configured"}

        url = f"{server_url.rstrip('/')}/api/v1/plugins/oss/check-in"
        payload = {"instance_id": self._oss_instance_id}
        body_bytes = _json.dumps(payload).encode("utf-8")
        headers = self.get_oss_instance_headers(body_bytes)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=body_bytes, headers={
                    "Content-Type": "application/json",
                    **headers,
                }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return {"ok": True}
                    text = await resp.text()
                    return {"ok": False, "error": f"HTTP {resp.status}: {text[:200]}"}
        except aiohttp.ClientError as exc:
            return {"ok": False, "error": str(exc)}

    def load_oss_instance_info(self):
        """
        从本地文件加载已注册的实例信息（重启后恢复）。
        路径由 settings.OSS_INSTANCE_INFO_FILE 指定。
        优先加载主文件，失败时尝试 .bak 备份。
        """
        import json as _json
        path = getattr(settings, "OSS_INSTANCE_INFO_FILE", None)
        if not path:
            return
        for candidate in [path, path + ".bak"]:
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                if data.get("instance_id") and data.get("instance_secret"):
                    self._oss_instance_id = data["instance_id"]
                    self._oss_instance_secret = data["instance_secret"]
                    logger.info(f"[OSS-Register] Restored instance info from {candidate}: {self._oss_instance_id}")  # i18n
                    return
            except FileNotFoundError:
                continue
            except Exception as exc:
                logger.warning(f"[OSS-Register] Failed to load instance info ({candidate}): {exc}")  # i18n
                continue

    def save_oss_instance_info(self):
        """
        将实例信息持久化到本地文件（重启后可恢复）。
        使用原子写入（先写临时文件再重命名）+ 备份旧文件。
        """
        import json as _json
        from datetime import datetime, timezone
        if not self._oss_instance_id:
            return
        path = getattr(settings, "OSS_INSTANCE_INFO_FILE", None)
        if not path:
            return
        data = {
            "instance_id": self._oss_instance_id,
            "instance_secret": self._oss_instance_secret,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                _json.dump(data, f, indent=2, ensure_ascii=False)
            if os.path.exists(path):
                bak_path = path + ".bak"
                try:
                    if os.path.exists(bak_path):
                        os.remove(bak_path)
                    os.rename(path, bak_path)
                except Exception as e:
                    logger.warning(f"Failed to backup instance info: {e}")
            os.rename(tmp_path, path)
            logger.info(f"[OSS-Register] Instance info saved to {path}")  # i18n
        except Exception as exc:
            logger.warning(f"[OSS-Register] Failed to save instance info: {exc}")  # i18n
            if os.path.exists(path + ".tmp"):
                try:
                    os.remove(path + ".tmp")
                except Exception as e:
                    logger.warning(f"Failed to remove temp file: {e}")

    # -------------------------------------------------------------------------
    # G-02/G-08: 插件沙箱资源限制 + 健康监控
    # -------------------------------------------------------------------------

    def _init_plugin_health(self, plugin_id: str) -> None:
        if plugin_id not in self._plugin_health:
            self._plugin_health[plugin_id] = {
                "errors": 0,
                "restarts": 0,
                "disabled": False,
                "last_error": None,
                "last_check": time.monotonic(),
            }

    def record_plugin_error(self, plugin_id: str, error: str = "") -> None:
        entry = self._plugin_health.get(plugin_id)
        if not entry:
            self._init_plugin_health(plugin_id)
            entry = self._plugin_health[plugin_id]
        entry["errors"] += 1
        entry["last_error"] = error
        threshold = int(getattr(settings, "PLUGIN_HEALTH_ERROR_THRESHOLD", 0) or 0)
        if threshold > 0 and entry["errors"] >= threshold:
            entry["disabled"] = True
            logger.warning(
                "Plugin %s has %d consecutive errors (threshold %d), auto-disabled",  # i18n
                plugin_id, entry["errors"], threshold,
            )

    def record_plugin_success(self, plugin_id: str) -> None:
        entry = self._plugin_health.get(plugin_id)
        if entry:
            entry["errors"] = 0

    def is_plugin_healthy(self, plugin_id: str) -> bool:
        entry = self._plugin_health.get(plugin_id)
        if not entry:
            return True
        return not entry.get("disabled", False)

    def check_plugin_disk_usage(self, plugin_id: str) -> int:
        """返回插件目录占用磁盘大小（MB），目录不存在返回0。"""
        dir_path = os.path.join(self.plugin_dir, plugin_id)
        if not os.path.isdir(dir_path):
            return 0
        total = 0
        for dirpath, _dirnames, filenames in os.walk(dir_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    logger.warning("OSError occurred")
        return total // (1024 * 1024)

    def check_plugin_disk_limit(self, plugin_id: str) -> bool:
        """检查插件磁盘占用是否超限。返回True表示OK，False表示超限。"""
        limit_mb = int(getattr(settings, "PLUGIN_SANDBOX_DISK_LIMIT_MB", 0) or 0)
        if limit_mb <= 0:
            return True
        usage_mb = self.check_plugin_disk_usage(plugin_id)
        if usage_mb > limit_mb:
            logger.warning(f"Plugin {plugin_id} disk usage {usage_mb}MB exceeds limit {limit_mb}MB")  # i18n
            return False
        return True

    async def start_health_check_loop(self) -> None:
        """启动插件健康检查后台循环。"""
        interval = int(getattr(settings, "PLUGIN_HEALTH_CHECK_INTERVAL_SECONDS", 0) or 0)
        if interval <= 0:
            return
        if self._health_check_task and not self._health_check_task.done():
            return
        self._health_check_task = asyncio.create_task(self._health_check_loop(interval))

    async def _health_check_loop(self, interval: int) -> None:
        """后台循环：定期检查插件健康状态。"""
        while True:
            try:
                await asyncio.sleep(interval)
                for pid in list(self.metadata.keys()):
                    try:
                        self.check_plugin_disk_limit(pid)
                    except Exception as e:
                        logger.debug(f"Health check disk for {pid}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    def stop_health_check_loop(self) -> None:
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            self._health_check_task = None

    async def start_license_refresh_subscriber(self) -> None:
        """订阅 Redis license:refresh:{tenant_id} 频道，收到续费推送后即时刷新本地授权缓存。
        仅在 PLUGIN_MARKETPLACE_ENABLED=True 时启动。
        """
        if not bool(getattr(settings, "PLUGIN_MARKETPLACE_ENABLED", False)):
            logger.debug("[LicenseRefresh] PLUGIN_MARKETPLACE_ENABLED=False, subscriber not started")
            return
        redis_url = getattr(settings, "REDIS_URL", None) or getattr(settings, "REDIS_HOST", "")  # I3 回退值不再硬编码localhost
        if not redis_url:
            return
        try:
            import aioredis
        except ImportError:
            try:
                from redis import asyncio as aioredis
            except ImportError:
                logger.debug("[LicenseRefresh] No async Redis client available, subscriber not started")
                return
        try:
            redis_client = aioredis.from_url(
                redis_url if isinstance(redis_url, str) and redis_url.startswith("redis://") else f"redis://{redis_url}:{getattr(settings, 'REDIS_PORT', 6379)}",
                decode_responses=True,
            )
            tenant_id = str(getattr(settings, "TENANT_ID", "") or "default").strip()
            channel = f"license:refresh:{tenant_id}"
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel)
            logger.info(f"[LicenseRefresh] Subscribed to {channel}")
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
                if msg and msg.get("type") == "message":
                    try:
                        data = json.loads(msg.get("data", "{}"))
                        event = data.get("event", "")
                        plugin_id = data.get("plugin_id", "")
                        if event == "payment_success" and plugin_id:
                            logger.info(f"[LicenseRefresh] Received payment_success for plugin {plugin_id}, refreshing license cache")
                            meta = self.metadata.get(plugin_id)
                            if meta and str((meta or {}).get("type") or "").lower() == "paid":
                                self._paid_license_last_ok.pop(plugin_id, None)
                                self._paid_license_recheck_mono.pop(plugin_id, None)
                                self._paid_plugin_license_recheck_now(plugin_id, meta or {})
                                logger.info(f"[LicenseRefresh] Plugin {plugin_id} license cache refreshed after payment")
                    except Exception as e:
                        logger.warning(f"[LicenseRefresh] Error processing message: {e}")
        except asyncio.CancelledError:
            pass  # intentional: asyncio cancellation
        except Exception as e:
            logger.warning(f"[LicenseRefresh] Subscriber error: {e}")


# Singleton
plugin_manager = PluginManager()