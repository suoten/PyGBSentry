"""SIP 消息解析与构造（RFC 3261）。

提供 :class:`SipMessage`，用于在 SIP 服务器、commander、handlers、transactions
等模块之间统一表示一条 SIP 请求或响应报文。

设计要点：
    * ``headers`` 字段同时支持字典风格访问（``headers["Via"] = ...``、
      ``headers.get("To")``，大小写敏感，使用规范头部名）与多值追加
      （``headers.add("Via", ...)``，例如 Via/Record-Route 可重复出现）。
    * :meth:`SipMessage.get_header` / :meth:`SipMessage.get_headers` 提供大小写
      不敏感的访问，并兼容 RFC 3261 紧凑形式（``v``/``i``/``t``/``f``/``m``/``u``）。
    * :meth:`SipMessage.parse` 接受 ``bytes`` 或 ``str``，解析后的 ``body`` 始终为
      ``str``（调用方约定，参见 response_handler.py 中 "C-17 msg.body已是str" 注释）。
    * :meth:`SipMessage.to_bytes` 在缺失时自动补全 ``Content-Length``，并将
      ``body`` 统一编码为 ``bytes``。

本模块绝不抛出顶层导入异常 —— 所有依赖均为标准库或已确认存在的项目内模块。
"""
from __future__ import annotations

import re
from typing import Iterator, Union

from loguru import logger


# ---------------------------------------------------------------------------
# 头部容器
# ---------------------------------------------------------------------------

# RFC 3261 紧凑形式 -> 规范名映射（大小写不敏感查找时使用）
_COMPACT_FORM_MAP = {
    "v": "via",
    "i": "call-id",
    "t": "to",
    "f": "from",
    "m": "contact",
    "u": "allow-events",
    "e": "encoding",
    "l": "content-length",
    "c": "content-type",
    "s": "subject",
    "k": "supported",
    "r": "refer-to",
    "o": "event",
    "b": "referred-by",
    "n": "identity",
    "d": "request-disposition",
    "x": "session-expires",
    "j": "reject-contact",
}


def _norm_name(name: str) -> str:
    """头部名归一化：小写并展开紧凑形式，用于大小写不敏感比较。"""
    key = (name or "").strip().lower()
    return _COMPACT_FORM_MAP.get(key, key)


class _Headers:
    """SIP 头部容器。

    内部以 ``dict[str, list[str]]`` 存储，键保留写入时的原始大小写（调用方使用
    规范名如 ``"Via"``、``"From"``、``"Call-ID"``）。字典风格操作（``[]``、
    ``get``、``in``）大小写**敏感**，与现有代码（handlers.py ``resp.headers.get("To")``
    等）保持一致；多值头部通过 :meth:`add` 追加，序列化时通过 :meth:`raw_items`
    保留每个值。
    """

    __slots__ = ("_data",)

    def __init__(self) -> None:
        """Internal helper:   init  ."""
        # 保持插入顺序（Python 3.7+ dict 有序）
        self._data: dict[str, list[str]] = {}

    # --- 字典风格写入（替换语义） ---
    def __setitem__(self, key: str, value: Union[str, list, tuple]) -> None:
        """Internal helper:   setitem  ."""
        if value is None:
            # 写入 None 等价于删除
            self._data.pop(key, None)
            return
        if isinstance(value, (list, tuple)):
            self._data[key] = [str(v) for v in value]
        else:
            self._data[key] = [str(value)]

    def __getitem__(self, key: str) -> str:
        """Internal helper:   getitem  ."""
        # 返回第一个值（大小写敏感），与原 dict 行为一致
        vals = self._data[key]
        return vals[0]

    def __delitem__(self, key: str) -> None:
        """Internal helper:   delitem  ."""
        del self._data[key]

    def __contains__(self, key: object) -> bool:
        """Internal helper:   contains  ."""
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        """Internal helper:   iter  ."""
        return iter(self._data)

    def __len__(self) -> int:
        """Internal helper:   len  ."""
        return len(self._data)

    def __bool__(self) -> bool:
        """Internal helper:   bool  ."""
        return bool(self._data)

    # --- 访问 ---
    def get(self, key: str, default=None):
        """大小写**敏感**取值，返回第一个值（与原 dict.get 一致）。"""
        vals = self._data.get(key)
        if not vals:
            return default
        return vals[0]

    def get_all(self, key: str) -> list[str]:
        """大小写敏感取值，返回该键的全部值列表（可能为空）。"""
        vals = self._data.get(key)
        return list(vals) if vals else []

    def add(self, key: str, value: str) -> None:
        """追加一个值到 ``key``（多值头部，如 Via/Record-Route）。"""
        if key in self._data:
            self._data[key].append(str(value))
        else:
            self._data[key] = [str(value)]

    def keys(self):
        """Keys."""
        return self._data.keys()

    def values(self):
        """迭代每个键的第一个值（dict 兼容）。"""
        for vals in self._data.values():
            yield vals[0]

    def items(self):
        """迭代 (key, first_value)，与普通 dict.items() 语义一致。"""
        for k, vals in self._data.items():
            yield k, vals[0]

    def raw_items(self):
        """迭代 (key, value)，保留多值（每个值单独返回），用于序列化。"""
        for k, vals in self._data.items():
            for v in vals:
                yield k, v

    def copy(self) -> "_Headers":
        """Copy."""
        new = _Headers()
        for k, vals in self._data.items():
            new._data[k] = list(vals)
        return new

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        """Internal helper:   repr  ."""
        return f"_Headers({dict(self._data)!r})"


# ---------------------------------------------------------------------------
# 解析用的正则
# ---------------------------------------------------------------------------

# From/To 头中的 ;tag=xxx
_TAG_RE = re.compile(r";\s*tag=([^;\s]+)", re.IGNORECASE)
# Via 头中的 ;branch=xxx
_VIA_BRANCH_RE = re.compile(r"(?:^|;)\s*branch=([^;\s]+)", re.IGNORECASE)
# CSeq: <seq> <method>
_CSEQ_RE = re.compile(r"^\s*(\d+)\s+([A-Za-z]+)\s*$")
# SIP-URI 中提取 host:port（用于 Contact 等属性的简单访问）


# ---------------------------------------------------------------------------
# SipMessage
# ---------------------------------------------------------------------------

class SipMessage:
    """SIP 请求或响应报文。

    构造请求时设置 ``method``/``uri``/``version``；构造响应时设置
    ``version``/``status_code``/``reason_phrase``。``version`` 缺省 ``"SIP/2.0"``。
    """

    __slots__ = (
        "method",
        "uri",
        "version",
        "status_code",
        "reason_phrase",
        "body",
        "headers",
        # 缓存原始起始行，便于调试 / 透传
        "_start_line_raw",
    )

    def __init__(self) -> None:
        """Internal helper:   init  ."""
        self.method: str = ""
        self.uri: str = ""
        self.version: str = "SIP/2.0"
        self.status_code: int | None = None
        self.reason_phrase: str = ""
        self.body: str = ""
        self.headers: _Headers = _Headers()
        self._start_line_raw: str = ""

    # ----------------------- 属性 -----------------------

    @property
    def is_request(self) -> bool:
        """是否为请求报文（有 method 且无 status_code）。"""
        return bool(self.method) and not self.status_code

    @property
    def is_response(self) -> bool:
        """是否为响应报文。"""
        return bool(self.status_code)

    @property
    def start_line(self) -> str:
        """返回起始行文本。"""
        if self._start_line_raw:
            return self._start_line_raw
        if self.status_code:
            return f"{self.version or 'SIP/2.0'} {self.status_code} {self.reason_phrase or ''}".rstrip()
        return f"{self.method or ''} {self.uri or ''} {self.version or 'SIP/2.0'}".strip()

    # --- 常用头部便捷访问 ---

    @property
    def call_id(self) -> str:
        """Call id."""
        return self.get_header("Call-ID")

    @property
    def from_header(self) -> str:
        """From header."""
        return self.get_header("From")

    @property
    def from_tag(self) -> str:
        """From tag."""
        m = _TAG_RE.search(self.from_header or "")
        return m.group(1) if m else ""

    @property
    def to_header(self) -> str:
        """To header."""
        return self.get_header("To")

    @property
    def to_tag(self) -> str:
        """To tag."""
        m = _TAG_RE.search(self.to_header or "")
        return m.group(1) if m else ""

    @property
    def cseq(self) -> str:
        """Cseq."""
        return self.get_header("CSeq")

    @property
    def cseq_num(self) -> int:
        """Cseq num."""
        m = _CSEQ_RE.match(self.cseq or "")
        if not m:
            return 0
        try:
            return int(m.group(1))
        except ValueError:
            return 0

    @property
    def cseq_method(self) -> str:
        """Cseq method."""
        m = _CSEQ_RE.match(self.cseq or "")
        return (m.group(2).upper() if m else "")

    @property
    def via_branch(self) -> str:
        """Via branch."""
        via = self.get_header("Via") or self.get_header("v")
        if not via:
            return ""
        m = _VIA_BRANCH_RE.search(via)
        return m.group(1) if m else ""

    @property
    def max_forwards(self) -> int:
        """Max forwards."""
        val = self.get_header("Max-Forwards")
        if not val:
            return 0
        try:
            return int(val.strip())
        except ValueError:
            return 0

    @property
    def contact(self) -> str:
        """Contact."""
        return self.get_header("Contact")

    # ----------------------- 头部访问（大小写不敏感） -----------------------

    def get_header(self, name: str, default: str = "") -> str:
        """大小写不敏感取头部第一个值；兼容紧凑形式（v/i/t/f/m...）。

        注意：``headers.get(name)`` 是大小写**敏感**的（保留写入时的规范名），
        而本方法做大小写不敏感匹配，适合解析来自对端的报文。
        """
        if not name:
            return default
        norm = _norm_name(name)
        for k, vals in self.headers._data.items():
            if _norm_name(k) == norm and vals:
                return vals[0]
        return default

    def get_headers(self, name: str) -> list[str]:
        """大小写不敏感取头部全部值（多值头部，如 Via）。"""
        if not name:
            return []
        norm = _norm_name(name)
        out: list[str] = []
        for k, vals in self.headers._data.items():
            if _norm_name(k) == norm:
                out.extend(vals)
        return out

    # ----------------------- 序列化 -----------------------

    def to_bytes(self) -> bytes:
        """将报文序列化为 ``bytes``。

        - 响应起始行：``SIP/2.0 <code> <reason>``
        - 请求起始行：``<method> <uri> SIP/2.0``
        - 自动补全 ``Content-Length``（若未显式设置）
        - ``body`` 接受 ``str`` 或 ``bytes``，统一输出 ``bytes``
        """
        # 起始行
        if self.status_code:
            start_line = f"{self.version or 'SIP/2.0'} {self.status_code} {self.reason_phrase or ''}".rstrip()
        else:
            start_line = f"{self.method or ''} {self.uri or ''} {self.version or 'SIP/2.0'}".strip()

        # body -> bytes
        if self.body is None:
            body_bytes = b""
        elif isinstance(self.body, bytes):
            body_bytes = self.body
        else:
            body_bytes = str(self.body).encode("utf-8", errors="replace")

        # 自动补全 Content-Length（若未设置则添加，避免对端等待）
        has_cl = False
        for k in self.headers.keys():
            if _norm_name(k) == "content-length":
                has_cl = True
                break
        if not has_cl:
            self.headers["Content-Length"] = str(len(body_bytes))

        # 拼接头区
        parts: list[bytes] = [start_line.encode("utf-8", errors="replace")]
        for k, v in self.headers.raw_items():
            parts.append(f"{k}: {v}".encode("utf-8", errors="replace"))
        # 头区结束空行 + body
        parts.append(b"")
        parts.append(body_bytes)
        return b"\r\n".join(parts)

    # ----------------------- 解析 -----------------------

    @classmethod
    def parse(cls, data) -> "SipMessage":
        """从 ``bytes`` 或 ``str`` 解析一条 SIP 报文。

        - 严格按照 ``\\r\\n\\r\\n`` 分割头区与 body；若 Content-Length 存在则按其截断 body，
          否则取分割后剩余全部内容。
        - ``body`` 设置为 ``str``（UTF-8 解码，errors='ignore'），与现有调用方约定一致。
        - 解析失败时记录警告并尽力返回部分填充的对象，不抛异常（调用方需容忍）。
        """
        msg = cls()
        if data is None:
            return msg
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="ignore")
        else:
            text = str(data)

        # 分割头区与 body（首个 \r\n\r\n）
        sep = "\r\n\r\n"
        idx = text.find(sep)
        if idx < 0:
            # 兼容仅 \n\n 的情况
            sep = "\n\n"
            idx = text.find(sep)
        if idx < 0:
            header_block = text
            body_text = ""
        else:
            header_block = text[:idx]
            body_text = text[idx + len(sep):]

        lines = header_block.split("\r\n")
        # 兼容 \n
        if len(lines) == 1:
            lines = header_block.split("\n")

        if not lines or not lines[0].strip():
            logger.warning("SipMessage.parse: empty start line")
            return msg

        # 起始行
        start_line = lines[0].rstrip("\r\n")
        msg._start_line_raw = start_line
        cls._parse_start_line(msg, start_line)

        # 头部
        for line in lines[1:]:
            line = line.rstrip("\r\n")
            if not line:
                continue
            # 折叠行（RFC 3261: 以空白开头的行是上一行的续行）
            if line[:1] in (" ", "\t") :
                # 续行：附加到上一个头（简单实现：追加空格）
                # 找到上一个写入的键
                last_key = None
                for k in list(msg.headers.keys()):
                    last_key = k
                if last_key is not None:
                    cur = msg.headers.get(last_key, "")
                    msg.headers[last_key] = (cur + " " + line.strip())
                continue
            ci = line.find(":")
            if ci <= 0:
                continue
            hname = line[:ci].strip()
            hval = line[ci + 1:].strip()
            # 多值头部使用 add，避免覆盖（如 Via）
            if _norm_name(hname) in ("via", "record-route", "route"):
                msg.headers.add(hname, hval)
            else:
                msg.headers[hname] = hval

        # body：按 Content-Length 截断
        cl_str = msg.get_header("Content-Length")
        if cl_str:
            try:
                cl = int(cl_str.strip())
                if cl >= 0 and cl <= len(body_text):
                    body_text = body_text[:cl]
            except ValueError:
                logger.debug("swallowed_exception", exc_info=True)
        msg.body = body_text
        return msg

    @staticmethod
    def _parse_start_line(msg: "SipMessage", start_line: str) -> None:
        """Internal helper:  parse start line."""
        s = start_line.strip()
        if not s:
            return
        # 响应：SIP/2.0 <code> <reason>
        if s.upper().startswith("SIP/2.0"):
            # 按空白拆分：SIP/2.0 200 OK
            parts = s.split(None, 2)
            msg.version = parts[0] if parts else "SIP/2.0"
            if len(parts) >= 2:
                try:
                    msg.status_code = int(parts[1])
                except ValueError:
                    msg.status_code = None
            if len(parts) >= 3:
                msg.reason_phrase = parts[2]
            return
        # 请求：<method> <uri> SIP/2.0
        parts = s.split()
        if len(parts) >= 3:
            msg.method = parts[0]
            msg.uri = parts[1]
            msg.version = parts[2]
        elif len(parts) == 2:
            msg.method = parts[0]
            msg.uri = parts[1]
            msg.version = "SIP/2.0"
        else:
            # 无法识别，保留原样
            msg.version = s

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        """Internal helper:   repr  ."""
        if self.status_code:
            return f"<SipMessage {self.version} {self.status_code} {self.reason_phrase}>"
        return f"<SipMessage {self.method} {self.uri} {self.version}>"
