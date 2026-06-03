import unittest


class TestHookUtils(unittest.TestCase):
    def test_is_stream_unreg_variants(self):
        from app.api.v1.endpoints.hook_utils import is_stream_unreg

        self.assertTrue(is_stream_unreg({"regist": False}))
        self.assertTrue(is_stream_unreg({"regist": 0}))
        self.assertTrue(is_stream_unreg({"registered": "0"}))
        self.assertTrue(is_stream_unreg({"alive": 0}))
        self.assertFalse(is_stream_unreg({"regist": True}))
        self.assertFalse(is_stream_unreg({}))


if __name__ == "__main__":
    unittest.main()
