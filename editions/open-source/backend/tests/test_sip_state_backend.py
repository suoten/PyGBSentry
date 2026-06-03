import asyncio
import pytest


class TestLocalSipStateBackend:
    @pytest.mark.asyncio
    async def test_register_and_notify_ssrc_waiter(self):
        from app.sip.state_backend import LocalSipStateBackend
        backend = LocalSipStateBackend()
        await backend.register_ssrc_waiter("1234567890")
        await backend.notify_ssrc_registered("1234567890")
        result = await backend.wait_ssrc_stream("1234567890", timeout=0.1)
        assert result is True

    @pytest.mark.asyncio
    async def test_unregister_ssrc_waiter(self):
        from app.sip.state_backend import LocalSipStateBackend
        backend = LocalSipStateBackend()
        await backend.register_ssrc_waiter("1234567890")
        await backend.unregister_ssrc_waiter("1234567890")
        result = await backend.wait_ssrc_stream("1234567890", timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_nonce_nc_check(self):
        from app.sip.state_backend import LocalSipStateBackend
        backend = LocalSipStateBackend()
        assert await backend.check_nonce_nc("user1", "nonce1", 1) is True
        assert await backend.check_nonce_nc("user1", "nonce1", 2) is True
        assert await backend.check_nonce_nc("user1", "nonce1", 1) is False

    @pytest.mark.asyncio
    async def test_invite_rate_limit(self):
        from app.sip.state_backend import LocalSipStateBackend
        backend = LocalSipStateBackend()
        allowed, _ = await backend.consume_invite_rate("tenant1", "device1", window=10.0, per_device=5, per_tenant=100)
        assert allowed is True


class TestSipStateBackendFactory:
    def test_get_local_backend(self):
        from app.sip.state_backend import get_sip_state_backend, LocalSipStateBackend
        # Reset singleton
        import app.sip.state_backend as mod
        mod._backend_instance = None
        backend = get_sip_state_backend()
        assert isinstance(backend, LocalSipStateBackend)
