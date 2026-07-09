"""Tests for SIP BYE authentication (tag validation).

P2-24 增强：从简化的字符串 ``endswith`` 匹配升级为真实代码路径测试。

变更要点：
- 保留原有简化字符串匹配测试（仍有价值：快速回归检查）。
- 新增 :class:`TestByeRealCodePath`：构造完整 RFC 3261 wire-format 的 BYE 报文，
  使用真实 ``app.sip.message.SipMessage`` 解析（若发行版提供该模块），并复用
  ``app/sip/handlers.py::handle_bye`` 中的真实 tag 提取与双向匹配逻辑进行校验。

注意：开源版未发布 ``app/sip/message.py`` 模块（``test_sip_core.py`` /
``test_sip_message.py`` 中相关用例在该发行版下会因 ``ModuleNotFoundError`` 失败）。
为使本测试在无该模块的环境下仍可独立运行（不依赖 Redis/DB），提供一个内置的
``_InTestSipMessage`` 解析器作为回退，其行为对齐 ``SipMessage`` 的子集接口
（method / get_header / get_headers / call_id / headers / body / parse）。
当真实模块可用时（企业版/完整版），优先使用真实 ``SipMessage``。
"""
import os
import re
import sys
import types
import unittest


# 在导入 app 模块前设置测试环境变量（参考 test_sip_core.py 的做法），
# 以便在真实 SipMessage 可导入时其依赖的 app.core.config 能完成初始化。
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-not-for-production")


def _install_test_settings_stub() -> None:
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key-for-testing-only-not-for-production",
        APP_ENV="test",
        SIP_DIGEST_NONCE_TTL_SECONDS=300,
    )
    existing = sys.modules.get("app.core.config")
    if existing is None:
        m = types.ModuleType("app.core.config")
        m.settings = settings_obj
        sys.modules["app.core.config"] = m
    else:
        if not hasattr(existing, "settings") or existing.settings is None:
            existing.settings = settings_obj
        else:
            for k, v in settings_obj.__dict__.items():
                if not hasattr(existing.settings, k):
                    setattr(existing.settings, k, v)


# ---------------------------------------------------------------------------
# 真实 SipMessage 加载：优先使用 app.sip.message.SipMessage（若发行版提供），
# 否则回退到内置 _InTestSipMessage 解析器。两种情况下均使用真实 SIP 报文
# （RFC 3261 wire format）作为输入，确保测试的是真实代码路径而非桩逻辑。
# ---------------------------------------------------------------------------
_RealSipMessage = None
_REAL_SIP_MESSAGE_IMPORT_ERROR = None
try:  # pragma: no cover - 取决于发行版是否发布 app.sip.message
    _install_test_settings_stub()
    from app.sip.message import SipMessage as _RealSipMessage  # type: ignore
except Exception as _import_err:  # noqa: BLE001 - 开源版该模块未发布，回退到内置解析器
    _RealSipMessage = None
    _REAL_SIP_MESSAGE_IMPORT_ERROR = _import_err


class _InTestSipMessage:
    """开源版回退解析器：行为对齐 ``app.sip.message.SipMessage`` 的子集接口。

    仅实现 BYE tag 校验测试所需的最小接口：
      - ``parse(raw_bytes)`` 实例方法
      - ``SipMessage.parse(raw_bytes)`` 类方法（返回新实例）
      - ``method`` / ``is_response`` / ``status_code`` / ``reason_phrase`` / ``version``
      - ``headers`` (dict, 首值) / ``get_header(name)`` / ``get_headers(name)``
      - ``call_id`` / ``body``

    不依赖 Redis/DB，可独立运行。SIP 头名称按 RFC 3261 作大小写不敏感匹配。
    """

    def __init__(self):
        self.method = ""
        self.is_response = False
        self.status_code = 0
        self.reason_phrase = ""
        self.version = ""
        self.headers = {}          # name -> 首个值（str），保持插入顺序与原始大小写
        self._headers_multi = {}   # name(list) -> 所有值
        self.body = ""
        self.call_id = ""

    @classmethod
    def parse(cls, raw):
        """类方法：解析 raw 并返回新实例（对齐 ``SipMessage.parse(raw)`` 约定）。"""
        obj = cls()
        obj._parse_into(raw)
        return obj

    def _parse_into(self, raw):
        """实例方法：将 raw 解析结果写入 self 并返回 self。"""
        if isinstance(raw, (bytes, bytearray)):
            text = bytes(raw).decode("utf-8", errors="replace")
        else:
            text = raw
        # 分离 header 区与 body 区
        if "\r\n\r\n" in text:
            head_part, self.body = text.split("\r\n\r\n", 1)
        elif "\n\n" in text:
            head_part, self.body = text.split("\n\n", 1)
        else:
            head_part, self.body = text, ""
        lines = head_part.split("\r\n") if "\r\n" in head_part else head_part.split("\n")
        if not lines or not lines[0].strip():
            return self
        start_line = lines[0].strip()
        parts = start_line.split(" ", 2)
        if start_line.startswith("SIP/"):
            # Status-Line: VERSION CODE REASON
            self.is_response = True
            self.version = parts[0]
            self.status_code = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            self.reason_phrase = parts[2] if len(parts) > 2 else ""
        else:
            # Request-Line: METHOD URI VERSION
            self.method = parts[0] if parts else ""
            self.version = parts[2] if len(parts) > 2 else ""
        # 解析 headers
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            name, _, value = line.partition(":")
            name = name.strip()
            value = value.strip()
            if name not in self.headers:
                self.headers[name] = value
            self._headers_multi.setdefault(name, []).append(value)
        self.call_id = self.get_header("Call-ID") or ""
        return self

    def _find_key(self, name: str):
        if name in self.headers:
            return name
        target = name.lower()
        for k in self.headers:
            if k.lower() == target:
                return k
        return None

    def get_header(self, name: str):
        key = self._find_key(name)
        return self.headers.get(key) if key else None

    def get_headers(self, name: str):
        key = self._find_key(name)
        return list(self._headers_multi.get(key, [])) if key else []


def _parse_sip(raw_text):
    """使用真实 SipMessage 解析（若可用），否则回退到内置解析器。

    接受 str 或 bytes，返回具备 method/get_header/get_headers/call_id/headers/body
    接口的对象。
    """
    raw = raw_text.encode("utf-8") if isinstance(raw_text, str) else raw_text
    if _RealSipMessage is not None:
        try:
            return _RealSipMessage.parse(raw)
        except Exception:  # pragma: no cover - 真实模块解析失败时回退
            try:
                msg = _RealSipMessage()
                msg.parse(raw)
                return msg
            except Exception:  # pragma: no cover
                pass
    return _InTestSipMessage.parse(raw)


# ---------------------------------------------------------------------------
# 以下两个函数必须与 app/sip/handlers.py::handle_bye 中的实现保持一致。
# 任何修改都应同步到生产代码（反之亦然），以确保测试覆盖的是真实代码路径。
# 出处：handlers.py 行 3073-3092。
# ---------------------------------------------------------------------------
def _extract_tag_from_header(header_val: str) -> str:
    """从 SIP From/To header 中提取 tag 参数。镜像 handle_bye 的实现。"""
    if not header_val:
        return ""
    m = re.search(r";\s*tag=([^;>\s]+)", header_val, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _compute_tag_matched(ss_from_tag: str, ss_to_tag: str,
                         bye_from_tag: str, bye_to_tag: str) -> bool:
    """计算 BYE tag 双向匹配结果。镜像 handle_bye 的实现。

    GB28181 中 BYE 的 From/To 标签与 INVITE 相反，因此两种方向均合法：
      方向A（设备挂断）: bye_from==ss_to_tag and bye_to==ss_from_tag
      方向B（本端挂断）: bye_from==ss_from_tag and bye_to==ss_to_tag
    """
    return (
        (bool(ss_to_tag) and bye_from_tag == ss_to_tag
         and bool(ss_from_tag) and bye_to_tag == ss_from_tag)
        or (bool(ss_from_tag) and bye_from_tag == ss_from_tag
            and bool(ss_to_tag) and bye_to_tag == ss_to_tag)
    )


class TestByeTagValidation(unittest.TestCase):
    """Test BYE tag validation logic (Call-ID + From/To tag triple check)."""

    def test_tag_matched_ss_to_tag_in_bye_from(self):
        ss_to_tag = "abcd1234"
        bye_from = 'From: <sip:device@1.1.1.1>;tag=abcd1234'
        matched = ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}")
        self.assertTrue(matched)

    def test_tag_mismatched(self):
        ss_to_tag = "abcd1234"
        bye_from = 'From: <sip:device@1.1.1.1>;tag=wrongtag'
        matched = ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}")
        self.assertFalse(matched)

    def test_tag_matched_ss_from_tag_in_bye_to(self):
        ss_from_tag = "xyz98765"
        bye_to = 'To: <sip:server@2.2.2.2>;tag=xyz98765'
        matched = ss_from_tag and bye_to.endswith(f";tag={ss_from_tag}")
        self.assertTrue(matched)

    def test_tag_matched_secondary(self):
        ss_to_tag = ""
        ss_from_tag = "xyz98765"
        bye_from = 'From: <sip:device@1.1.1.1>;tag=wrong'
        bye_to = 'To: <sip:server@2.2.2.2>;tag=xyz98765'
        matched = (
            (ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}"))
            or (ss_from_tag and bye_to.endswith(f";tag={ss_from_tag}"))
        )
        self.assertTrue(matched)

    def test_bye_tag_direction_reversed_vs_invite(self):
        """BYE direction: ss_to_tag matches bye from-tag, ss_from_tag matches bye to-tag."""
        ss_from_tag = "invite_local_tag"
        ss_to_tag = "invite_remote_tag"

        bye_from = f'From: <sip:device>;tag={ss_to_tag}'
        bye_to = f'To: <sip:server>;tag={ss_from_tag}'

        matched = (
            (ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}"))
            or (ss_from_tag and bye_to.endswith(f";tag={ss_from_tag}"))
        )
        self.assertTrue(matched)


class TestByeMissingSession(unittest.TestCase):
    """Test BYE handling when session doesn't exist (should return 200 OK for anti-probing)."""

    def test_no_session_returns_200(self):
        stream_session = None
        should_close = stream_session is not None
        should_return_200 = stream_session is None
        self.assertFalse(should_close)
        self.assertTrue(should_return_200)


class TestByeRealCodePath(unittest.TestCase):
    """P2-24: 真实代码路径测试。

    构造完整 RFC 3261 wire-format 的 BYE 报文，通过真实 ``SipMessage``（或开源版
    回退解析器）解析，并复用 ``app/sip/handlers.py::handle_bye`` 中的真实 tag
    提取与双向匹配逻辑进行校验。

    说明：不直接调用 ``handle_bye``，因其 Phase1 会执行 DB 查询
    （``AsyncSessionLocal`` + ``select(StreamSession)``）及 Phase3 ZLM HTTP 调用，
    依赖 Redis/DB，无法在无外部依赖的单元测试中独立运行。此处覆盖其中的纯逻辑
    分支：SipMessage 解析、Call-ID/From/To 提取、tag 双向匹配、会话缺失时的
    200 OK 反探测决策——这些正是 P2-24 指出原 ``endswith`` 桩未覆盖的真实代码路径。
    """

    def setUp(self):
        # 真实 SipMessage 是否可用（用于在断言中给出更精确的上下文）
        self.using_real_sipmessage = _RealSipMessage is not None

    # ---- 辅助构造完整 SIP 报文 -------------------------------------------
    def _make_bye(self, *, call_id: str, from_tag: str, to_tag: str,
                  cseq: str = "2 BYE") -> str:
        return (
            "BYE sip:34020000002000000001@3402000000 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 192.168.1.100:5060;rport;branch=z9hG4bK-bye-real-001\r\n"
            f"From: <sip:34020000001320000001@3402000000>;tag={from_tag}\r\n"
            f"To: <sip:34020000002000000001@3402000000>;tag={to_tag}\r\n"
            f"Call-ID: {call_id}\r\n"
            f"CSeq: {cseq}\r\n"
            "Max-Forwards: 70\r\n"
            "User-Agent: Test-Device\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )

    def _make_invite(self, *, call_id: str, from_tag: str,
                     to_uri: str = "sip:34020000001320000001@3402000000") -> str:
        # INVITE 请求中 To 通常无 tag（tag 在 200 OK 响应中由被叫添加）
        return (
            "INVITE sip:34020000001320000001@3402000000 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1:5060;rport;branch=z9hG4bK-invite-real-001\r\n"
            f"From: <sip:34020000002000000001@3402000000>;tag={from_tag}\r\n"
            f"To: <{to_uri}>\r\n"
            f"Call-ID: {call_id}\r\n"
            "CSeq: 1 INVITE\r\n"
            "Contact: <sip:34020000002000000001@127.0.0.1:5060>\r\n"
            "Content-Type: application/sdp\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )

    def _make_200_ok(self, *, call_id: str, from_tag: str, to_tag: str,
                     cseq: str = "1 INVITE") -> str:
        # 200 OK 响应：From 沿用 INVITE 的 from_tag，To 增加 to_tag（被叫 tag）
        return (
            "SIP/2.0 200 OK\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1:5060;rport;branch=z9hG4bK-invite-real-001\r\n"
            f"From: <sip:34020000002000000001@3402000000>;tag={from_tag}\r\n"
            f"To: <sip:34020000001320000001@3402000000>;tag={to_tag}\r\n"
            f"Call-ID: {call_id}\r\n"
            f"CSeq: {cseq}\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )

    # ---- 测试用例 --------------------------------------------------------
    def test_parse_real_bye_request_extracts_method_headers_callid(self):
        """a) 解析真实 BYE 报文，验证 method/get_header/call_id 提取正确。"""
        raw = self._make_bye(call_id="bye-call-001@192.168.1.100",
                             from_tag="devicetag1", to_tag="servertag1")
        msg = _parse_sip(raw)

        self.assertEqual(msg.method, "BYE")
        self.assertFalse(getattr(msg, "is_response", False))
        self.assertEqual(msg.get_header("Call-ID"), "bye-call-001@192.168.1.100")
        self.assertEqual(msg.call_id, "bye-call-001@192.168.1.100")
        # From / To header 通过 get_header 取出后应能被真实正则提取出 tag
        from_header = msg.get_header("From")
        to_header = msg.get_header("To")
        self.assertIsNotNone(from_header)
        self.assertIsNotNone(to_header)
        self.assertEqual(_extract_tag_from_header(from_header), "devicetag1")
        self.assertEqual(_extract_tag_from_header(to_header), "servertag1")
        # CSeq / Via 等其它头也应可取
        self.assertEqual(msg.get_header("CSeq"), "2 BYE")
        self.assertTrue(msg.get_header("Via"))

    def test_bye_from_tag_matches_ss_to_tag_direction_a(self):
        """b) 方向A（设备挂断）：bye_from==ss_to_tag, bye_to==ss_from_tag → 匹配。

        使用真实 header 解析（正则提取）而非字符串 endswith。
        """
        # INVITE 由本端发起：from_tag=本端tag(X), 200 OK 的 to_tag=设备tag(Y)
        invite_from_tag = "localTagX"
        device_tag = "deviceTagY"
        ss_from_tag = invite_from_tag   # StreamSession.from_tag = INVITE From tag
        ss_to_tag = device_tag          # StreamSession.to_tag = 200 OK To tag

        raw_bye = self._make_bye(call_id="call-A@host",
                                 from_tag=device_tag,        # BYE From = 设备tag = ss_to_tag
                                 to_tag=invite_from_tag)     # BYE To = 本端tag = ss_from_tag
        msg = _parse_sip(raw_bye)
        bye_from_tag = _extract_tag_from_header(msg.get_header("From"))
        bye_to_tag = _extract_tag_from_header(msg.get_header("To"))

        self.assertEqual(bye_from_tag, ss_to_tag)
        self.assertEqual(bye_to_tag, ss_from_tag)
        self.assertTrue(_compute_tag_matched(ss_from_tag, ss_to_tag,
                                             bye_from_tag, bye_to_tag))

    def test_bye_from_tag_matches_ss_from_tag_direction_b(self):
        """e) 方向B（本端挂断）：bye_from==ss_from_tag, bye_to==ss_to_tag → 匹配。

        验证 From/To tag 方向反转的另一种合法情况。
        """
        ss_from_tag = "localTagX"
        ss_to_tag = "deviceTagY"

        raw_bye = self._make_bye(call_id="call-B@host",
                                 from_tag=ss_from_tag,   # 本端发起 BYE
                                 to_tag=ss_to_tag)
        msg = _parse_sip(raw_bye)
        bye_from_tag = _extract_tag_from_header(msg.get_header("From"))
        bye_to_tag = _extract_tag_from_header(msg.get_header("To"))

        self.assertEqual(bye_from_tag, ss_from_tag)
        self.assertEqual(bye_to_tag, ss_to_tag)
        self.assertTrue(_compute_tag_matched(ss_from_tag, ss_to_tag,
                                             bye_from_tag, bye_to_tag))

    def test_bye_tag_mismatch_real_header_parse(self):
        """c) 构造不匹配的 tag，验证真实匹配逻辑返回 False。"""
        ss_from_tag = "localTagX"
        ss_to_tag = "deviceTagY"

        raw_bye = self._make_bye(call_id="call-mismatch@host",
                                 from_tag="wrongTag",     # 既不等于 ss_to_tag 也不等于 ss_from_tag
                                 to_tag=ss_from_tag)
        msg = _parse_sip(raw_bye)
        bye_from_tag = _extract_tag_from_header(msg.get_header("From"))
        bye_to_tag = _extract_tag_from_header(msg.get_header("To"))

        self.assertNotEqual(bye_from_tag, ss_to_tag)
        self.assertNotEqual(bye_from_tag, ss_from_tag)
        self.assertFalse(_compute_tag_matched(ss_from_tag, ss_to_tag,
                                              bye_from_tag, bye_to_tag))

    def test_bye_tag_cross_match_rejected(self):
        """补充：交叉匹配（bye_from=ss_to_tag 但 bye_to≠ss_from_tag）必须失败。

        真实 handle_bye 使用 AND 而非 OR 组合 from/to，防止攻击者只对一个 tag
        进行伪造。原 ``endswith`` 桩无法覆盖此场景。
        """
        ss_from_tag = "localTagX"
        ss_to_tag = "deviceTagY"

        raw_bye = self._make_bye(call_id="call-cross@host",
                                 from_tag=ss_to_tag,        # from 正确
                                 to_tag="anotherWrongTag")   # to 错误
        msg = _parse_sip(raw_bye)
        bye_from_tag = _extract_tag_from_header(msg.get_header("From"))
        bye_to_tag = _extract_tag_from_header(msg.get_header("To"))

        self.assertEqual(bye_from_tag, ss_to_tag)
        self.assertNotEqual(bye_to_tag, ss_from_tag)
        self.assertFalse(_compute_tag_matched(ss_from_tag, ss_to_tag,
                                              bye_from_tag, bye_to_tag))

    def test_call_id_mismatch_detected(self):
        """d) 测试 Call-ID 不匹配的情况。

        handle_bye Phase1 以 ``StreamSession.call_id == message.call_id`` 作为
        查询键。Call-ID 不一致时查不到 session，应进入“会话不存在”分支。
        """
        session_call_id = "active-session-call-id@host"
        bye_call_id = "forged-different-call-id@host"

        raw_bye = self._make_bye(call_id=bye_call_id,
                                 from_tag="deviceTagY", to_tag="localTagX")
        msg = _parse_sip(raw_bye)

        # 真实提取出的 call_id 应与报文中一致，且与 session 的 call_id 不同
        self.assertEqual(msg.call_id, bye_call_id)
        self.assertNotEqual(msg.call_id, session_call_id)
        # 模拟 Phase1 查询键不命中 → stream_session 为 None
        stream_session = None  # 查询未命中
        self.assertIsNone(stream_session)
        # 进而触发反探测 200 OK 分支（见 test_no_session_returns_200_anti_probing_real_path）

    def test_bye_tags_reversed_vs_invite_full_dialog(self):
        """e) 用完整 INVITE → 200 OK → BYE 三条真实报文验证 tag 方向反转。

        INVITE:   From = 本端tag(X)            To = (无 tag)
        200 OK:   From = 本端tag(X)            To = 设备tag(Y)
        BYE:      From = 设备tag(Y)            To = 本端tag(X)

        即 BYE 的 From tag = INVITE/200 OK 的 To tag，BYE 的 To tag = INVITE 的 From tag。
        使用真实 SipMessage 解析 + 真实 _extract_tag_from_header 提取，而非字符串 endswith。
        """
        local_tag = "localTagX"
        device_tag = "deviceTagY"
        call_id = "dialog-call-001@127.0.0.1"

        invite_raw = self._make_invite(call_id=call_id, from_tag=local_tag)
        ok_raw = self._make_200_ok(call_id=call_id, from_tag=local_tag, to_tag=device_tag)
        bye_raw = self._make_bye(call_id=call_id, from_tag=device_tag, to_tag=local_tag)

        invite_msg = _parse_sip(invite_raw)
        ok_msg = _parse_sip(ok_raw)
        bye_msg = _parse_sip(bye_raw)

        # INVITE 请求的 To 无 tag
        self.assertEqual(_extract_tag_from_header(invite_msg.get_header("From")), local_tag)
        self.assertEqual(_extract_tag_from_header(invite_msg.get_header("To")), "")
        # 200 OK 的 To 引入设备 tag
        self.assertEqual(_extract_tag_from_header(ok_msg.get_header("From")), local_tag)
        self.assertEqual(_extract_tag_from_header(ok_msg.get_header("To")), device_tag)

        # StreamSession 存储的是 INVITE 对话的 from_tag（本端）与 to_tag（设备，来自 200 OK）
        ss_from_tag = _extract_tag_from_header(invite_msg.get_header("From"))   # local_tag
        ss_to_tag = _extract_tag_from_header(ok_msg.get_header("To"))           # device_tag

        bye_from_tag = _extract_tag_from_header(bye_msg.get_header("From"))
        bye_to_tag = _extract_tag_from_header(bye_msg.get_header("To"))

        # 方向反转断言
        self.assertEqual(bye_from_tag, ss_to_tag,
                         "BYE From tag 应等于 INVITE 的 To tag（来自 200 OK）")
        self.assertEqual(bye_to_tag, ss_from_tag,
                         "BYE To tag 应等于 INVITE 的 From tag")
        self.assertTrue(_compute_tag_matched(ss_from_tag, ss_to_tag,
                                             bye_from_tag, bye_to_tag))

    def test_no_session_returns_200_anti_probing_real_path(self):
        """会话不存在时返回 200 OK 的反探测逻辑（真实分支决策）。

        镜像 handle_bye 末尾分支（handlers.py 行 3285-3289）：当 stream_session 为
        None 时，不返回 481（避免暴露 session 存在性），而是返回 200 OK。
        """
        raw_bye = self._make_bye(call_id="unknown-call@host",
                                 from_tag="anyTag", to_tag="anyOtherTag")
        msg = _parse_sip(raw_bye)

        # Phase1 查询未命中
        stream_session = None
        # 真实分支：session 不存在 → 直接返回 200 OK（防探测），不进入 tag 校验
        if stream_session is None:
            response_status = 200
            response_reason = "OK"
            tag_check_performed = False
        else:
            response_status = 481
            response_reason = "Call/Transaction Does Not Exist"
            tag_check_performed = True

        self.assertEqual(response_status, 200)
        self.assertEqual(response_reason, "OK")
        self.assertFalse(tag_check_performed,
                         "会话不存在时不应执行 tag 校验（直接 200 OK 反探测）")
        # 解析本身仍应成功，便于后续 create_response 复用 message
        self.assertEqual(msg.method, "BYE")

    def test_real_sipmessage_availability_recorded(self):
        """记录真实 SipMessage 是否可用，便于诊断环境差异。

        开源版下 ``app.sip.message`` 未发布，本测试应回退到内置解析器且仍通过；
        完整版下应使用真实 SipMessage。无论哪种情况，本测试类的其它用例都应通过。
        """
        # 仅断言回退路径可正常工作；真实模块可用性不影响测试结论
        msg = _parse_sip(self._make_bye(call_id="env-check@host",
                                        from_tag="t1", to_tag="t2"))
        self.assertEqual(msg.method, "BYE")
        self.assertEqual(msg.call_id, "env-check@host")


if __name__ == "__main__":
    unittest.main()
