import unittest
from unittest import mock


class TestZlmRtpServerService(unittest.IsolatedAsyncioTestCase):
    async def test_open_rtp_server_raises_on_nonzero_code(self):
        """非零 code 且无特定关键词时分类为 media_service_error（fallback）。

        UPDATED [2026-07-17]: 原 category="unknown" 已重构为更具描述性的
        "media_service_error"（与 _response.py / stream_play.py 中 reason_code
        一致），status_code 从 502 调整为 503（媒体节点服务端错误）。
        """
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
                    re_use_port=True,
                    enable_hls=1,
                    enable_mp4=0,
                )
        self.assertEqual(ctx.exception.category, "media_service_error")
        self.assertEqual(ctx.exception.status_code, 503)

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
                    re_use_port=True,
                    enable_hls=1,
                    enable_mp4=0,
                )
        self.assertEqual(ctx.exception.category, "media_port_exhausted")
        self.assertEqual(ctx.exception.status_code, 503)

    async def test_open_rtp_server_classifies_connect_error(self):
        """ConnectError 分类为 media_node_unreachable。

        UPDATED [2026-07-17]: 原 category="network_error" 已重构为更具描述性的
        "media_node_unreachable"（与 stream_play.py / stream_session_service.py 中
        reason_code 一致），便于在流媒体调度链路中统一识别媒体节点不可达场景。
        """
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
                    re_use_port=True,
                    enable_hls=1,
                    enable_mp4=0,
                )
        self.assertEqual(ctx.exception.category, "media_node_unreachable")
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
