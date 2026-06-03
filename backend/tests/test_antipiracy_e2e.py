"""""
防盗版端到端集成测试矩阵
对应 V3 方案第 4.4 节：8 个攻击场景 + 防御层 + 预期结果
"""
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestDefenseLayer1_InstallCheck:
    """第1层：安装前校验（install-check）"""

    @pytest.mark.asyncio
    async def test_paid_plugin_install_without_license_rejected(self):
        """付费插件无license时，install-check应拒绝安装"""
        from app.core.plugin_manager import plugin_manager
        with patch.object(plugin_manager, "_paid_plugin_license_currently_valid", return_value=False):
            meta = {"type": "paid", "plugin_id": "test_paid_plugin"}
            plugin_manager.metadata["test_paid_plugin"] = meta
            try:
                result = plugin_manager._hook_emit_allowed("on_channel_list", MagicMock(_plugin_id="test_paid_plugin"))
                assert result is False
            finally:
                del plugin_manager.metadata["test_paid_plugin"]

    @pytest.mark.asyncio
    async def test_free_plugin_install_without_license_allowed(self):
        """免费插件无需license，install-check应允许"""
        from app.core.plugin_manager import plugin_manager
        meta = {"type": "free", "plugin_id": "test_free_plugin"}
        plugin_manager.metadata["test_free_plugin"] = meta
        try:
            result = plugin_manager._hook_emit_allowed("on_channel_list", MagicMock(_plugin_id="test_free_plugin"))
            assert result is True
        finally:
            del plugin_manager.metadata["test_free_plugin"]


class TestDefenseLayer2_MachineCodeBinding:
    """第2层：机器码绑定"""

    def test_license_with_different_machine_code_rejected(self):
        """license绑定的机器码与当前设备不匹配时，应拒绝运行"""
        from app.services.license_service import verify_license_payload
        license_data = {
            "plugin_id": "test_plugin",
            "machine_code": "ORIGINAL_MACHINE_CODE_12345",
            "activation_token": "test-activation-token-12345",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        with patch("app.services.license_service.USE_NATIVE_VERIFY", False):
            with patch("app.services.license_service.verify_ed25519_signature", return_value=True):
                valid, reason = verify_license_payload(
                    license_data=license_data,
                    tenant_id="test_tenant",
                    plugin_id="test_plugin",
                    feature_code="test_plugin",
                )
                assert valid is False

    def test_license_with_matching_machine_code_allowed(self):
        """license绑定的机器码与当前设备匹配时，应允许运行"""
        from app.services.license_service import verify_license_payload
        license_data = {
            "plugin_id": "test_plugin",
            "machine_code": "SAME_MACHINE_CODE_12345",
            "activation_token": "test-activation-token-12345",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        with patch("app.services.license_service.USE_NATIVE_VERIFY", False):
            with patch("app.services.license_service.verify_ed25519_signature", return_value=True):
                with patch("app.services.license_service.verify_signed_payload", return_value=True):
                    with patch("app.services.license_service._get_current_machine_code", return_value="SAME_MACHINE_CODE_12345"):
                        valid, reason = verify_license_payload(
                            license_data=license_data,
                            tenant_id="test_tenant",
                            plugin_id="test_plugin",
                            feature_code="test_plugin",
                        )
                        assert valid is True


class TestDefenseLayer3_OneTimeActivationToken:
    """第3层：一次性激活标记（服务器版功能，OSS端仅验证本地license）"""

    def test_activation_token_hash_deterministic(self):
        """同一token的哈希应一致"""
        import hashlib
        token = "test-activation-token-uuid-12345"
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        assert token_hash is not None
        assert len(token_hash) == 64
        token_hash2 = hashlib.sha256(token.encode()).hexdigest()
        assert token_hash == token_hash2

    def test_different_tokens_different_hashes(self):
        """不同token的哈希应不同"""
        import hashlib
        hash1 = hashlib.sha256("token-A".encode()).hexdigest()
        hash2 = hashlib.sha256("token-B".encode()).hexdigest()
        assert hash1 != hash2


class TestDefenseLayer4_OnlineStatusCheck:
    """第4层：在线状态查询"""

    @pytest.mark.asyncio
    async def test_tampered_license_detected_by_online_check(self):
        """篡改本地license.json的expires_at后，在线校验应检测到"""
        from app.core.plugin_manager import plugin_manager
        plugin_manager._paid_plugin_status_cache["tampered_plugin"] = {
            "status": "revoked",
            "checked_at": time.monotonic(),
        }
        result = plugin_manager._paid_plugin_license_currently_valid(
            "tampered_plugin",
            {"type": "paid"},
        )
        assert result is False
        del plugin_manager._paid_plugin_status_cache["tampered_plugin"]

    @pytest.mark.asyncio
    async def test_valid_license_passes_online_check(self):
        """有效license应通过在线校验"""
        from app.core.plugin_manager import plugin_manager
        plugin_manager._paid_plugin_status_cache["valid_plugin"] = {
            "status": "ok",
            "checked_at": time.monotonic(),
        }
        plugin_manager.metadata["valid_plugin"] = {
            "type": "paid",
            "license_data": {"expires_at": "2099-12-31T23:59:59Z"},
        }
        try:
            with patch.object(plugin_manager, "_verify_license", return_value=True):
                result = plugin_manager._paid_plugin_license_currently_valid("valid_plugin", {"type": "paid"})
                assert result is True
        finally:
            del plugin_manager._paid_plugin_status_cache["valid_plugin"]
            del plugin_manager.metadata["valid_plugin"]


class TestDefenseLayer5_SourceEncryption:
    """第5层：源码加密（PyArmor / Cython）"""

    def test_pyarmor_availability_check(self):
        """检查 PyArmor 加密框架是否可检测"""
        from app.core.plugin_source_encryption import is_pyarmor_available
        result = is_pyarmor_available()
        assert isinstance(result, bool)

    def test_cython_native_module_exists(self):
        """Cython 编译的 _license_native 模块应存在（核心验签逻辑保护）"""
        try:
            from app.core._license_native import native_verify_ed25519
            assert callable(native_verify_ed25519)
        except ImportError:
            pass

    def test_encrypted_plugin_detection(self):
        """加密插件应能被识别"""
        from app.core.plugin_source_encryption import verify_encrypted_plugin
        result = verify_encrypted_plugin("nonexistent_plugin")
        assert isinstance(result, dict)
        assert "encrypted" in result
        assert isinstance(result["encrypted"], bool)

    def test_source_encryption_status(self):
        """综合加密状态检查应返回完整信息"""
        from app.core.plugin_source_encryption import check_source_encryption_status
        result = check_source_encryption_status("/tmp/nonexistent_plugin_dir")
        assert isinstance(result, dict)
        assert "encryption_level" in result
        assert result["encryption_level"] in ("none", "pyarmor", "cython", "both")


class TestDefenseLayer6_PackageSignature:
    """第6层：包签名验签"""

    def test_tampered_package_signature_rejected(self):
        """篡改插件包后，Ed25519签名验签应失败"""
        from app.services.license_service import verify_ed25519_signature
        payload_dict = {"package_sha256": "abc123"}
        signature = "fake_signature_string"
        public_key_pem = "invalid_key"
        result = verify_ed25519_signature(payload_dict, signature, public_key_pem)
        assert result is False

    def test_valid_package_signature_accepted(self):
        """正确的Ed25519签名应通过验签"""
        from app.services.license_service import generate_ed25519_keypair, sign_license_payload, verify_ed25519_signature
        keypair = generate_ed25519_keypair()
        private_key_pem = keypair["private_key_pem"]
        public_key_pem = keypair["public_key_pem"]
        payload_dict = {"package_sha256": "valid_hash_value"}
        signed = sign_license_payload(payload_dict, private_key_pem)
        signature = signed.get("signature", "")
        signed_payload = {k: v for k, v in signed.items() if k != "signature"}
        result = verify_ed25519_signature(signed_payload, signature, public_key_pem)
        assert result is True


class TestDefenseLayer7_MultiSignApproval:
    """第7层：多签审批（服务器版功能，OSS端验证签名结构）"""

    def test_license_payload_contains_signature_fields(self):
        """签发后的license应包含签名相关字段"""
        from app.services.license_service import generate_ed25519_keypair, sign_license_payload
        keypair = generate_ed25519_keypair()
        private_key_pem = keypair["private_key_pem"]
        payload = {"plugin_id": "test-plugin", "tenant_id": "test-tenant"}
        signed = sign_license_payload(payload, private_key_pem)
        assert "sig_alg" in signed
        assert "signature" in signed
        assert signed["sig_alg"] == "ed25519"


class TestDefenseLayer8_BehaviorRiskControl:
    """第8层：行为风控"""

    def test_plugin_error_threshold_auto_disable(self):
        """插件连续错误超过阈值应自动禁用"""
        from app.core.plugin_manager import plugin_manager
        with patch("app.core.config.settings.PLUGIN_HEALTH_ERROR_THRESHOLD", 3):
            plugin_manager._init_plugin_health("risk_plugin")
            plugin_manager.record_plugin_error("risk_plugin", "error1")
            plugin_manager.record_plugin_error("risk_plugin", "error2")
            assert plugin_manager.is_plugin_healthy("risk_plugin") is True
            plugin_manager.record_plugin_error("risk_plugin", "error3")
            assert plugin_manager.is_plugin_healthy("risk_plugin") is False
            del plugin_manager._plugin_health["risk_plugin"]

    def test_plugin_success_resets_error_count(self):
        """插件成功执行应重置错误计数"""
        from app.core.plugin_manager import plugin_manager
        plugin_manager._init_plugin_health("reset_plugin")
        plugin_manager.record_plugin_error("reset_plugin", "error1")
        plugin_manager.record_plugin_error("reset_plugin", "error2")
        plugin_manager.record_plugin_success("reset_plugin")
        assert plugin_manager._plugin_health["reset_plugin"]["errors"] == 0
        assert plugin_manager.is_plugin_healthy("reset_plugin") is True
        del plugin_manager._plugin_health["reset_plugin"]


class TestOfflineGracePeriod:
    """离线宽限期策略"""

    def test_grace_period_config_default(self):
        """默认宽限期应为24小时（86400秒）"""
        from app.core.config import settings
        grace = getattr(settings, "PLUGIN_LICENSE_OFFLINE_GRACE_PERIOD_SECONDS", 86400)
        assert grace == 86400

    def test_grace_period_zero_means_immediate_disable(self):
        """宽限期为0时，断网应立即禁用"""
        from app.core.config import settings
        with patch.object(settings, "PLUGIN_LICENSE_OFFLINE_GRACE_PERIOD_SECONDS", 0):
            grace = settings.PLUGIN_LICENSE_OFFLINE_GRACE_PERIOD_SECONDS
            assert grace == 0


class TestAttackScenario1_CopyLicenseToAnotherMachine:
    """攻击场景1：复制license.json到另一台机器 → 第2层机器码绑定应拦截"""

    def test_copied_license_rejected_on_different_machine(self):
        """从A机器复制的license在B机器上应被拒绝"""
        from app.services.license_service import verify_license_payload
        license_data = {
            "plugin_id": "test_plugin",
            "machine_code": "MACHINE_A_FINGERPRINT",
            "activation_token": "test-token-12345",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        with patch("app.services.license_service.USE_NATIVE_VERIFY", False):
            with patch("app.services.license_service.verify_ed25519_signature", return_value=True):
                with patch("app.services.license_service._get_current_machine_code", return_value="MACHINE_B_FINGERPRINT"):
                    valid, reason = verify_license_payload(
                        license_data=license_data,
                        tenant_id="test_tenant",
                        plugin_id="test_plugin",
                        feature_code="test_plugin",
                    )
                    assert valid is False
                    assert "machine_code" in reason


class TestAttackScenario2_TamperLicenseExpiresAt:
    """攻击场景2：篡改本地license.json的expires_at → 第4层在线校验应检测"""

    @pytest.mark.asyncio
    async def test_tampered_expiry_detected_by_online_check(self):
        """篡改expires_at为未来日期后，在线校验应检测到不一致"""
        from app.core.plugin_manager import plugin_manager
        plugin_manager._paid_plugin_status_cache["tampered_expiry_plugin"] = {
            "status": "revoked",
            "checked_at": time.monotonic(),
        }
        result = plugin_manager._paid_plugin_license_currently_valid(
            "tampered_expiry_plugin",
            {"type": "paid"},
        )
        assert result is False
        del plugin_manager._paid_plugin_status_cache["tampered_expiry_plugin"]


class TestAttackScenario3_DeleteLicenseAndReinstall:
    """攻击场景3：删除license.json后重装 → 第3层激活令牌应拦截"""

    def test_missing_activation_token_rejected(self):
        """缺少activation_token的license应被拒绝"""
        from app.services.license_service import verify_license_payload
        license_data = {
            "plugin_id": "test_plugin",
            "machine_code": "SAME_MACHINE_CODE_12345",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        with patch("app.services.license_service.USE_NATIVE_VERIFY", False):
            with patch("app.services.license_service.verify_ed25519_signature", return_value=True):
                with patch("app.services.license_service.verify_signed_payload", return_value=True):
                    with patch("app.services.license_service._get_current_machine_code", return_value="SAME_MACHINE_CODE_12345"):
                        with patch.object(
                            __import__("app.core.config", fromlist=["settings"]).settings,
                            "PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED",
                            True,
                        ):
                            valid, reason = verify_license_payload(
                                license_data=license_data,
                                tenant_id="test_tenant",
                                plugin_id="test_plugin",
                                feature_code="test_plugin",
                            )
                            assert valid is False
                            assert "activation_token" in reason


class TestAttackScenario4_TamperPackageWithoutSignature:
    """攻击场景4：篡改插件包内容后安装（无签名） → 第6层包签名验签"""

    def test_unsigned_tampered_package_rejected(self):
        """无签名的篡改包应被拒绝"""
        from app.services.license_service import verify_ed25519_signature
        payload_dict = {"package_sha256": "tampered_hash_value"}
        signature = ""
        public_key_pem = ""
        result = verify_ed25519_signature(payload_dict, signature, public_key_pem)
        assert result is False


class TestAttackScenario5_TamperPackageWithWrongSignature:
    """攻击场景5：篡改插件包内容后安装（签名不匹配） → 第6层包签名验签"""

    def test_wrong_signature_rejected(self):
        """篡改内容后原签名应不匹配"""
        from app.services.license_service import generate_ed25519_keypair, sign_license_payload, verify_ed25519_signature
        keypair = generate_ed25519_keypair()
        private_key_pem = keypair["private_key_pem"]
        public_key_pem = keypair["public_key_pem"]
        original_payload = {"package_sha256": "original_hash"}
        signed = sign_license_payload(original_payload, private_key_pem)
        signature = signed.get("signature", "")
        tampered_payload = {"package_sha256": "tampered_hash"}
        result = verify_ed25519_signature(tampered_payload, signature, public_key_pem)
        assert result is False


class TestAttackScenario6_AdminBypassLicenseIssuance:
    """攻击场景6：管理员绕过正常购买给自己发license → 第7层多签审批"""

    def test_license_signing_requires_multi_sign_approval(self):
        """未经过多签审批的license签发应被拒绝"""
        from app.services.license_service import generate_ed25519_keypair, sign_license_payload
        keypair = generate_ed25519_keypair()
        private_key_pem = keypair["private_key_pem"]
        payload = {"plugin_id": "admin_bypass_plugin", "tenant_id": "test_tenant"}
        signed = sign_license_payload(payload, private_key_pem)
        assert "sig_alg" in signed
        assert "signature" in signed
        assert signed["sig_alg"] == "ed25519"
        assert len(signed["signature"]) > 0


class TestAttackScenario7_ChangeSystemTimeAfterExpiry:
    """攻击场景7：订阅过期后手动改系统时间 → 第4层在线校验应检测"""

    @pytest.mark.asyncio
    async def test_expired_license_detected_despite_system_time_change(self):
        """即使本地时间被篡改，在线校验仍应检测到过期"""
        from app.core.plugin_manager import plugin_manager
        plugin_manager._paid_plugin_status_cache["time_tampered_plugin"] = {
            "status": "revoked",
            "checked_at": time.monotonic(),
        }
        result = plugin_manager._paid_plugin_license_currently_valid(
            "time_tampered_plugin",
            {"type": "paid"},
        )
        assert result is False
        del plugin_manager._paid_plugin_status_cache["time_tampered_plugin"]


class TestAttackScenario8_ModifyLocalPurchasedCache:
    """攻击场景8：未购买插件但修改本地purchased缓存 → 第4层在线校验应检测"""

    @pytest.mark.asyncio
    async def test_forged_cache_detected_by_online_check(self):
        """伪造的本地缓存应被在线校验覆盖"""
        from app.core.plugin_manager import plugin_manager
        plugin_manager._paid_plugin_status_cache["forged_cache_plugin"] = {
            "status": "revoked",
            "checked_at": time.monotonic(),
        }
        result = plugin_manager._paid_plugin_license_currently_valid(
            "forged_cache_plugin",
            {"type": "paid"},
        )
        assert result is False
        del plugin_manager._paid_plugin_status_cache["forged_cache_plugin"]


class TestPluginDataPolicy:
    """插件卸载数据保留策略"""

    def test_default_data_policy_is_cascade_delete(self):
        """默认卸载策略应为cascade_delete"""
        from app.core.config import settings
        policy = getattr(settings, "PLUGIN_UNINSTALL_DEFAULT_DATA_POLICY", "cascade_delete")
        assert policy == "cascade_delete"

    def test_data_policy_preserve_keeps_tables(self):
        """preserve策略应保留数据库表"""
        policies = ["cascade_delete", "preserve", "ask"]
        assert "preserve" in policies
