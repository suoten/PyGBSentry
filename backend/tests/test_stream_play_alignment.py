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


class TestStreamPlayAlignment(unittest.IsolatedAsyncioTestCase):
    async def test_build_full_play_response_contains_standard_envelope(self):
        from app.api.v1.endpoints import stream as mod

        result = await mod._build_full_play_response(
            db=None,
            app_name="live",
            stream_id="34010300001310000002",
            stream_type="auto",
            selected_node=None,
            media_host="127.0.0.1",
            media_port=8880,
            node_host="127.0.0.1",
            node_http_port=8880,
            is_embedded_node=True,
            zlm_probe_ok=True,
            zlm_stream_ready=True,
            media_item={
                "matched_app": "live",
                "matched_stream": "34010300001310000002",
                "codec": "h265",
            },
            result={
                "sdp_ip": "1.1.1.1",
                "media_port": 30000,
                "media_protocol": "UDP",
                "stream_session_id": "sess-1",
                "ssrc": "12345",
                "call_id": "call-1",
            },
            node_id="node-1",
        )

        self.assertEqual(result["code"], 200)
        self.assertEqual(result["msg"], "ok")
        self.assertEqual(result["data"]["app"], "live")
        self.assertEqual(result["data"]["stream"], "34010300001310000002")
        self.assertEqual(result["data"]["node_id"], "node-1")
        self.assertIn("flv", result["data"])
        self.assertIn("hls", result["data"])
        self.assertIn("rtsp", result["data"])

    def test_map_play_stream_error_returns_structured_port_error(self):
        from app.api.v1.endpoints import stream as mod

        exc = RuntimeError("Call ZLM openRtpServer failed after 2 attempts. last_error=(node=x, error=port exhausted)")
        http_exc = mod._map_play_stream_error(exc)

        self.assertEqual(http_exc.status_code, 503)
        self.assertEqual(http_exc.detail["reason_code"], "media_port_exhausted")
        self.assertIn("port", http_exc.detail["message"].lower())


if __name__ == "__main__":
    unittest.main()
