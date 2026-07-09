import unittest
from unittest import mock


class TestZlmRtpServerService(unittest.IsolatedAsyncioTestCase):
    async def test_open_rtp_server_raises_on_nonzero_code(self):
        from app.services import zlm_rtp_server_service as mod

        class Resp:
            status_code = 200
            text = '{}'
            def json(self):
                return {"code": -1, "msg": "failed"}

        class Client:
            async def post(self, url, data=None, timeout=None):
                return Resp()

        with mock.patch.object(mod, "get_http_client", new=mock.AsyncMock(return_value=Client())):
            with self.assertRaises(mod.ZlmApiError) as ctx:
                await mod.open_rtp_server(
                    host="127.0.0.1",
                    http_port=80,
                    secret="s",
                    port=30000,
                    tcp_mode=0,
                    app="live",
                    stream_id="x",
                    ssrc="0100000001",
                    re_use_port="1",
                    enable_hls=1,
                    enable_mp4=0,
                )
        self.assertEqual(ctx.exception.category, "unknown")
        self.assertEqual(ctx.exception.status_code, 502)

    async def test_open_rtp_server_classifies_port_exhausted(self):
        from app.services import zlm_rtp_server_service as mod

        class Resp:
            status_code = 200
            text = '{}'
            def json(self):
                return {"code": -1, "msg": "端口已被占用"}

        class Client:
            async def post(self, url, data=None, timeout=None):
                return Resp()

        with mock.patch.object(mod, "get_http_client", new=mock.AsyncMock(return_value=Client())):
            with self.assertRaises(mod.ZlmApiError) as ctx:
                await mod.open_rtp_server(
                    host="127.0.0.1",
                    http_port=80,
                    secret="s",
                    port=30000,
                    tcp_mode=0,
                    app="live",
                    stream_id="x",
                    ssrc="0100000001",
                    re_use_port="1",
                    enable_hls=1,
                    enable_mp4=0,
                )
        self.assertEqual(ctx.exception.category, "media_port_exhausted")
        self.assertEqual(ctx.exception.status_code, 503)

    async def test_open_rtp_server_classifies_connect_error(self):
        from app.services import zlm_rtp_server_service as mod

        class Client:
            async def post(self, url, data=None, timeout=None):
                raise mod.httpx.ConnectError("boom")

        with mock.patch.object(mod, "get_http_client", new=mock.AsyncMock(return_value=Client())):
            with self.assertRaises(mod.ZlmApiError) as ctx:
                await mod.open_rtp_server(
                    host="127.0.0.1",
                    http_port=80,
                    secret="s",
                    port=30000,
                    tcp_mode=0,
                    app="live",
                    stream_id="x",
                    ssrc="0100000001",
                    re_use_port="1",
                    enable_hls=1,
                    enable_mp4=0,
                )
        self.assertEqual(ctx.exception.category, "network_error")
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
