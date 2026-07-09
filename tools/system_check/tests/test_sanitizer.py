"""tests for tools.system_check.shared.sanitizer — 敏感 key 检测、值脱敏、嵌套 dict。"""

from __future__ import annotations

import unittest

from tools.system_check.shared.sanitizer import Sanitizer


class TestIsSensitiveKey(unittest.TestCase):
    def test_sensitive_keys_detected(self):
        for key in [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "access_key",
            "private_key",
            "credential",
        ]:
            with self.subTest(key=key):
                self.assertTrue(Sanitizer.is_sensitive_key(key), f"应识别 {key} 为敏感 key")

    def test_case_insensitive(self):
        self.assertTrue(Sanitizer.is_sensitive_key("Password"))
        self.assertTrue(Sanitizer.is_sensitive_key("PASSWORD"))
        self.assertTrue(Sanitizer.is_sensitive_key("Api_Key"))
        self.assertTrue(Sanitizer.is_sensitive_key("X-Token"))

    def test_substring_match(self):
        # 子串也命中（如 user_password、auth_token、db_secret）
        self.assertTrue(Sanitizer.is_sensitive_key("user_password"))
        self.assertTrue(Sanitizer.is_sensitive_key("auth_token"))
        self.assertTrue(Sanitizer.is_sensitive_key("db_secret"))
        self.assertTrue(Sanitizer.is_sensitive_key("x_api_key"))
        self.assertTrue(Sanitizer.is_sensitive_key("refreshToken"))

    def test_non_sensitive_keys(self):
        for key in ["username", "email", "device_id", "channel_no", "method", "path", "id"]:
            with self.subTest(key=key):
                self.assertFalse(Sanitizer.is_sensitive_key(key))

    def test_empty_key(self):
        self.assertFalse(Sanitizer.is_sensitive_key(""))


class TestMaskValue(unittest.TestCase):
    def test_long_value_masked_with_prefix_and_suffix(self):
        value = "abcdefghij"  # len = 10
        masked = Sanitizer.mask_value(value, visible_prefix=3, visible_suffix=3)
        self.assertEqual(masked, "abc***hij")

    def test_short_value_returns_stars(self):
        # len <= visible_prefix + visible_suffix (默认 3+3=6) 时返回 "***"
        self.assertEqual(Sanitizer.mask_value("abc"), "***")
        self.assertEqual(Sanitizer.mask_value("abcdef"), "***")  # 恰好等于阈值
        self.assertEqual(Sanitizer.mask_value(""), "***")

    def test_just_above_threshold(self):
        # len = 7 > 6 应保留首尾各 3 字符
        masked = Sanitizer.mask_value("abcdefg", visible_prefix=3, visible_suffix=3)
        self.assertEqual(masked, "abc***efg")

    def test_custom_visible_lengths(self):
        self.assertEqual(Sanitizer.mask_value("123456789", visible_prefix=2, visible_suffix=2), "12***89")
        # 自定义阈值下短值返回 "***"
        self.assertEqual(Sanitizer.mask_value("abc", visible_prefix=2, visible_suffix=2), "***")


class TestSanitizeDict(unittest.TestCase):
    def test_sensitive_string_value_is_masked(self):
        data = {"password": "super-secret-value", "username": "alice"}
        result = Sanitizer.sanitize_dict(data)
        self.assertEqual(result["password"], "sup***lue")
        self.assertEqual(result["username"], "alice")

    def test_non_string_sensitive_value_left_as_is(self):
        # sanitize_dict 仅在 value 为 str 时才 mask
        data = {"token": 12345, "secret": None, "api_key": ["a", "b"]}
        result = Sanitizer.sanitize_dict(data)
        self.assertEqual(result["token"], 12345)
        self.assertIsNone(result["secret"])
        self.assertEqual(result["api_key"], ["a", "b"])

    def test_nested_dict_recursively_sanitized(self):
        data = {
            "user": {
                "username": "bob",
                "password": "very-long-password",
                "profile": {"api_key": "sk-1234567890abcdef"},
            },
            "token": "tok-abcdefghij",
        }
        result = Sanitizer.sanitize_dict(data)
        self.assertEqual(result["user"]["username"], "bob")
        self.assertEqual(result["user"]["password"], "ver***ord")
        self.assertEqual(result["user"]["profile"]["api_key"], "sk-***def")
        # "tok-abcdefghij" -> 首 3 "tok" + 尾 3 "hij"
        self.assertEqual(result["token"], "tok***hij")

    def test_list_of_dicts_sanitized(self):
        data = {
            "items": [
                {"username": "a", "password": "abcdefg"},
                {"username": "b", "password": "hijklmn"},
            ],
            "count": 2,
        }
        result = Sanitizer.sanitize_dict(data)
        self.assertEqual(result["items"][0]["username"], "a")
        self.assertEqual(result["items"][0]["password"], "abc***efg")
        self.assertEqual(result["items"][1]["password"], "hij***lmn")
        self.assertEqual(result["count"], 2)

    def test_list_of_scalars_unchanged(self):
        data = {"tags": ["a", "b", "c"]}
        result = Sanitizer.sanitize_dict(data)
        self.assertEqual(result["tags"], ["a", "b", "c"])

    def test_empty_dict(self):
        self.assertEqual(Sanitizer.sanitize_dict({}), {})

    def test_does_not_mutate_input(self):
        data = {"password": "supersecret", "username": "x"}
        original = dict(data)
        Sanitizer.sanitize_dict(data)
        self.assertEqual(data, original)

    def test_nested_list_inside_dict(self):
        data = {
            "users": [
                {"name": "a", "credentials": {"token": "secret-value-123"}},
            ],
        }
        result = Sanitizer.sanitize_dict(data)
        self.assertEqual(result["users"][0]["name"], "a")
        self.assertEqual(result["users"][0]["credentials"]["token"], "sec***123")


if __name__ == "__main__":
    unittest.main()
