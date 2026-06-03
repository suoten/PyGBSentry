import unittest
from unittest import mock


class DummyDB:
    async def execute(self, *args, **kwargs):
        raise RuntimeError("skip db query in unit test")


class TestMediaNodeSelection(unittest.IsolatedAsyncioTestCase):
    async def test_select_best_db_node_returns_none_when_single_node_unhealthy(self):
        from app.core import media_nodes_db as mod

        node = mod.RuntimeMediaNode(
            id="node-1",
            host="127.0.0.1",
            http_port=80,
            rtp_port=30000,
            public_host="127.0.0.1",
            public_http_port=80,
            secret="secret",
        )

        with mock.patch.object(mod, "list_db_media_nodes", new=mock.AsyncMock(return_value=[node])):
            with mock.patch.object(mod, "_async_get_stream_count", new=mock.AsyncMock(return_value=(node, 999999, False))):
                selected = await mod.select_best_db_node(DummyDB())

        self.assertIsNone(selected)

    async def test_select_best_db_node_picks_alive_node(self):
        from app.core import media_nodes_db as mod

        node_1 = mod.RuntimeMediaNode(
            id="node-1",
            host="127.0.0.1",
            http_port=80,
            rtp_port=30000,
            public_host="127.0.0.1",
            public_http_port=80,
            secret="secret",
        )
        node_2 = mod.RuntimeMediaNode(
            id="node-2",
            host="127.0.0.2",
            http_port=81,
            rtp_port=30001,
            public_host="127.0.0.2",
            public_http_port=81,
            secret="secret",
        )

        async def fake_stream_count(node):
            if node.id == "node-1":
                return node, 5, True
            return node, 1, True

        with mock.patch.object(mod, "list_db_media_nodes", new=mock.AsyncMock(return_value=[node_1, node_2])):
            with mock.patch.object(mod, "_async_get_stream_count", side_effect=fake_stream_count):
                selected = await mod.select_best_db_node(DummyDB())

        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, "node-2")


class TestStreamPlayAlignment(unittest.TestCase):
    def test_build_play_success_response_contains_standard_envelope(self):
        from app.api.v1.endpoints import stream as mod

        payload = mod._build_play_success_response(
            app_name="live",
            stream_id="34010300001310000002",
            token="abc",
            urls={
                "flv": "http://127.0.0.1:8880/live/34010300001310000002.live.flv?token=abc",
                "hls": "http://127.0.0.1:8880/live/34010300001310000002/hls.m3u8?token=abc",
                "rtc": "http://127.0.0.1:8880/index/api/webrtc?app=live&stream=34010300001310000002&type=play&token=abc",
                "rtcs": None,
            },
            codec="h265",
            media_server_id="node-1",
            media_info={"app": "live", "stream": "34010300001310000002"},
            result={"sdp_ip": "1.1.1.1", "media_port": 30000, "media_protocol": "UDP", "selection_reason": "auto"},
            zlm_probe_ok=True,
            zlm_stream_ready=True,
            webrtc_supported=True,
            webrtc_hint="",
            stream_type="auto",
        )

        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["msg"], "成功")
        self.assertEqual(payload["data"]["app"], "live")
        self.assertEqual(payload["data"]["stream"], "34010300001310000002")
        self.assertEqual(payload["data"]["mediaServerId"], "node-1")
        self.assertEqual(payload["data"]["streamType"], "auto")
        self.assertEqual(payload["flv"], payload["data"]["flv"])
        self.assertEqual(payload["webrtc"], payload["data"]["rtc"])

    def test_map_play_stream_error_returns_structured_port_error(self):
        from app.api.v1.endpoints import stream as mod

        exc = RuntimeError("Call ZLM openRtpServer failed after 2 attempts. last_error=(node=x, error=port exhausted)")
        http_exc = mod._map_play_stream_error(exc)

        self.assertEqual(http_exc.status_code, 503)
        self.assertEqual(http_exc.detail["reason_code"], "media_port_exhausted")
        self.assertIn("端口", http_exc.detail["message"])


if __name__ == "__main__":
    unittest.main()
