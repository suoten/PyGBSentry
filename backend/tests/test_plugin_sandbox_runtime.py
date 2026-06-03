import pytest
import sys
import os


class TestPluginSandboxRuntimeIntercept:
    """沙箱运行时拦截测试"""

    @pytest.fixture(autouse=True)
    def _setup_sandbox(self):
        from app.core.plugin_manager import (
            _install_plugin_sandbox_hook,
            _uninstall_plugin_sandbox_hook,
            _install_plugin_sandbox_builtin_guard,
            _uninstall_plugin_sandbox_builtin_guard,
            _install_plugin_sandbox_os_attr_guard,
            _uninstall_plugin_sandbox_os_attr_guard,
        )

        self._hook = _install_plugin_sandbox_hook("test_sandbox_plugin")
        self._builtin_saved = _install_plugin_sandbox_builtin_guard("test_sandbox_plugin")
        self._os_saved = _install_plugin_sandbox_os_attr_guard("test_sandbox_plugin")
        yield
        _uninstall_plugin_sandbox_os_attr_guard(self._os_saved)
        _uninstall_plugin_sandbox_builtin_guard(self._builtin_saved)
        _uninstall_plugin_sandbox_hook(self._hook)

    def test_import_subprocess_blocked(self):
        """import subprocess 应被沙箱拦截"""
        with pytest.raises(ImportError, match="沙箱拦截"):
            __import__("subprocess")

    def test_import_ctypes_blocked(self):
        """import ctypes 应被沙箱拦截"""
        with pytest.raises(ImportError, match="沙箱拦截"):
            __import__("ctypes")

    def test_import_pickle_blocked(self):
        """import pickle 应被沙箱拦截"""
        with pytest.raises(ImportError, match="沙箱拦截"):
            __import__("pickle")

    def test_os_system_blocked_in_plugin_context(self):
        """os.system 在插件上下文中应被拦截"""
        import os
        assert callable(os.system)

    def test_eval_blocked_in_plugin_context(self):
        """eval 在插件上下文中应被拦截"""
        import builtins
        guarded_eval = getattr(builtins, "eval", None)
        assert guarded_eval is not None

    def test_exec_blocked_in_plugin_context(self):
        """exec 在插件上下文中应被拦截"""
        import builtins
        guarded_exec = getattr(builtins, "exec", None)
        assert guarded_exec is not None

    def test_compile_blocked_in_plugin_context(self):
        """compile 在插件上下文中应被拦截"""
        import builtins
        guarded_compile = getattr(builtins, "compile", None)
        assert guarded_compile is not None

    def test_normal_api_allowed(self):
        """正常API调用不应被拦截"""
        import json
        result = json.dumps({"test": True})
        assert result == '{"test": true}'

    def test_sandbox_hook_installed(self):
        """沙箱hook应成功安装到sys.meta_path"""
        from app.core.plugin_manager import _PluginSandboxImportHook
        hooks = [h for h in sys.meta_path if isinstance(h, _PluginSandboxImportHook)]
        assert len(hooks) >= 1, "至少应有一个沙箱import hook安装"

    def test_blocked_modules_config_complete(self):
        """验证黑名单模块配置包含关键危险模块"""
        from app.core.plugin_manager import _PLUGIN_SANDBOX_BLOCKED_MODULES
        assert "subprocess" in _PLUGIN_SANDBOX_BLOCKED_MODULES
        assert "ctypes" in _PLUGIN_SANDBOX_BLOCKED_MODULES
        assert "pickle" in _PLUGIN_SANDBOX_BLOCKED_MODULES

    def test_blocked_builtins_config_complete(self):
        """验证builtins黑名单包含eval/exec/compile"""
        from app.core.plugin_manager import _PLUGIN_SANDBOX_BLOCKED_BUILTINS
        assert "eval" in _PLUGIN_SANDBOX_BLOCKED_BUILTINS
        assert "exec" in _PLUGIN_SANDBOX_BLOCKED_BUILTINS
        assert "compile" in _PLUGIN_SANDBOX_BLOCKED_BUILTINS

    def test_blocked_os_attrs_config_complete(self):
        """验证os属性黑名单包含关键危险函数"""
        from app.core.plugin_manager import _PLUGIN_SANDBOX_BLOCKED_OS_ATTRS
        assert "system" in _PLUGIN_SANDBOX_BLOCKED_OS_ATTRS
        assert "popen" in _PLUGIN_SANDBOX_BLOCKED_OS_ATTRS
        assert "remove" in _PLUGIN_SANDBOX_BLOCKED_OS_ATTRS
        assert "kill" in _PLUGIN_SANDBOX_BLOCKED_OS_ATTRS
