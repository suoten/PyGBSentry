from __future__ import annotations
from loguru import logger

from collections.abc import Iterable, Iterator, MutableMapping
from typing import Optional, Union
import re

_SIP_ABBREVIATIONS = {
    "f": "from",
    "t": "to",
    "v": "via",
    "i": "call-id",
    "m": "contact",
    "c": "content-type",
    "l": "content-length",
    "o": "event",
    "s": "subject",
    "k": "supported",
    "u": "allow-events",
    "e": "content-encoding",
    "x": "session-expires",
}

_CANONICAL_HEADER_NAMES = {
    "from": "From",
    "to": "To",
    "via": "Via",
    "call-id": "Call-ID",
    "contact": "Contact",
    "content-type": "Content-Type",
    "content-length": "Content-Length",
    "cseq": "CSeq",
    "max-forwards": "Max-Forwards",
    "user-agent": "User-Agent",
    "expires": "Expires",
    "authorization": "Authorization",
    "www-authenticate": "WWW-Authenticate",
    "subject": "Subject",
    "allow": "Allow",
    "accept": "Accept",
    "event": "Event",
    "subscription-state": "Subscription-State",
    "record-route": "Record-Route",
    "route": "Route",
    "date": "Date",
    "server": "Server",
    "retry-after": "Retry-After",
    "x-trace-id": "X-Trace-ID",
    "supported": "Supported",
    "require": "Require",
    "proxy-require": "Proxy-Require",
    "rseq": "RSeq",
    "rack": "RAck",
}


def _normalize_header_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    nl = n.lower()
    return _SIP_ABBREVIATIONS.get(nl, nl)


def _canonical_header_name(name: str) -> str:
    nl = _normalize_header_name(name)
    return _CANONICAL_HEADER_NAMES.get(nl, name.strip())


class SipHeaders(MutableMapping[str, str]):
    def __init__(self):
        self._items: list[tuple[str, str]] = []

    def _norm(self, key: str) -> str:
        return _normalize_header_name(key)

    def add(self, key: str, value: str) -> None:
        if not key:
            return
        self._items.append((key, value))

    def get_all(self, key: str) -> list[str]:
        nk = self._norm(key)
        if not nk:
            return []
        out: list[str] = []
        for k, v in self._items:
            if self._norm(k) == nk:
                out.append(v)
        return out

    def pop_all(self, key: str) -> list[str]:
        nk = self._norm(key)
        if not nk:
            return []
        kept: list[tuple[str, str]] = []
        removed: list[str] = []
        for k, v in self._items:
            if self._norm(k) == nk:
                removed.append(v)
            else:
                kept.append((k, v))
        self._items = kept
        return removed

    def iter_raw_items(self) -> Iterator[tuple[str, str]]:
        return iter(self._items)

    def __getitem__(self, key: str) -> str:
        vals = self.get_all(key)
        if not vals:
            raise KeyError(key)
        return vals[0]

    def __setitem__(self, key: str, value: str) -> None:
        self.pop_all(key)
        canonical = _canonical_header_name(key)
        self._items.append((canonical, value))

    def __delitem__(self, key: str) -> None:
        removed = self.pop_all(key)
        if not removed:
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for k, _ in self._items:
            nk = self._norm(k)
            if nk and nk not in seen:
                seen.add(nk)
                yield k

    def __len__(self) -> int:
        seen: set[str] = set()
        for k, _ in self._items:
            nk = self._norm(k)
            if nk:
                seen.add(nk)
        return len(seen)

    def items(self) -> Iterable[tuple[str, str]]:  # type: ignore[override]
        for k in self:
            yield (k, self[k])

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:  # type: ignore[override]
        vals = self.get_all(key)
        return vals[0] if vals else default


class SipMessage:
    def __init__(self):
        self.method: str = ""
        self.uri: str = ""
        self.headers: SipHeaders = SipHeaders()
        self._body_bytes: bytes = b""
        self._body_cache: str | None = None  # FIXED: I11 body解码缓存，避免每次访问重新解码
        self.version: str = "SIP/2.0"

        # Specific for Response
        self.status_code: int = 0
        self.reason_phrase: str = ""

    @property
    def is_request(self) -> bool:
        return self.method != "" and self.status_code == 0

    @property
    def is_response(self) -> bool:
        return self.status_code != 0

    @property
    def call_id(self) -> str:
        return self.get_header("Call-ID") or ""

    @property
    def cseq(self) -> str:
        return self.get_header("CSeq") or ""

    @property
    def from_header(self) -> str:
        return self.get_header("From") or ""

    @property
    def to_header(self) -> str:
        return self.get_header("To") or ""

    @property
    def body(self) -> str:
        # FIXED: I11 首次解码后缓存结果，后续访问直接返回缓存值
        if self._body_cache is not None:
            return self._body_cache
        if not self._body_bytes:
            return ""
        for enc in ("utf-8", "gb18030", "gbk", "gb2312"):
            try:
                self._body_cache = self._body_bytes.decode(enc)
                return self._body_cache
            except UnicodeDecodeError:
                continue
        self._body_cache = self._body_bytes.decode("latin-1", errors="replace")
        return self._body_cache

    @body.setter
    def body(self, value: Union[str, bytes]):
        self._body_cache = None  # FIXED: I11 body被重新赋值时清除缓存
        if isinstance(value, str):
            declared = ""
            m = re.search(r'<\?xml[^>]*encoding\s*=\s*[\'"]([^\'"]+)[\'"]', value, re.IGNORECASE)
            if m:
                declared = (m.group(1) or "").strip().lower()
            enc = "utf-8"
            if declared in {"gb2312", "gbk", "gb18030"}:
                enc = declared
            self._body_bytes = value.encode(enc, errors="replace")
        else:
            self._body_bytes = value

    def get_header(self, name: str) -> Optional[str]:
        return self.headers.get(name)

    def get_headers(self, name: str) -> list[str]:
        return self.headers.get_all(name)

    @staticmethod
    def parse(data: bytes) -> 'SipMessage':
        msg = SipMessage()

        # Split header and body (兼容 \r\n\r\n 和 \n\n)
        sep = b"\r\n\r\n"
        if sep not in data and b"\n\n" in data:
            sep = b"\n\n"
        parts = data.split(sep, 1)
        header_bytes = parts[0]
        body_bytes = parts[1] if len(parts) > 1 else b""

        try:
            header_str = header_bytes.decode('utf-8')
        except UnicodeDecodeError:
            for _enc in ("gb18030", "gbk", "gb2312"):
                try:
                    header_str = header_bytes.decode(_enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                header_str = header_bytes.decode('latin-1')

        # 兼容 \r\n 和 \n 行分隔
        lines = header_str.replace("\r\n", "\n").split("\n")
        if not lines or not lines[0]:
            raise ValueError("Empty SIP message")

        # Parse First Line
        first_line = lines[0]
        parts = first_line.split(" ", 2)
        if first_line.startswith("SIP/2.0"):
            if len(parts) < 2: raise ValueError("Malformed Status Line")
            msg.version = parts[0]
            try:
                msg.status_code = int(parts[1])
            except ValueError:
                raise ValueError(f"Invalid status code in Status Line: '{parts[1]}'")
            msg.reason_phrase = parts[2] if len(parts) > 2 else ""
        else:
            if len(parts) < 3: raise ValueError("Malformed Request Line")
            msg.method = parts[0]
            msg.uri = parts[1]
            msg.version = parts[2]

        # Parse Headers
        current_header: str | None = None
        last_item_index: int | None = None
        for line in lines[1:]:
            if not line:
                continue
            if line[0] in " \t" and current_header:
                if last_item_index is not None:
                    k, v = msg.headers._items[last_item_index]
                    msg.headers._items[last_item_index] = (k, v + " " + line.strip())
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                current_header = key.strip()
                msg.headers.add(current_header, value.strip())
                last_item_index = len(msg.headers._items) - 1

        content_length = msg.get_header("Content-Length") or msg.get_header("l") or ""
        if content_length:
            try:
                n = int(str(content_length).strip())
                if n >= 0:
                    # FIXED: Content-Length不匹配时记录告警，便于排查NVR报文问题
                    actual_len = len(body_bytes)
                    if actual_len < n:
                        logger.warning(
                            "SIP Content-Length mismatch: declared %d bytes but only %d available (truncated body)",
                            n, actual_len
                        )
                    body_bytes = body_bytes[:n]
            except Exception as e:
                logger.warning(f"Error: {e}")
        msg._body_bytes = body_bytes

        return msg

    _MULTI_VALUE_HEADERS = frozenset({"via", "contact", "record-route", "route"})

    def to_bytes(self) -> bytes:
        if self.is_response:
            first_line = f"{self.version} {self.status_code} {self.reason_phrase}"
        else:
            first_line = f"{self.method} {self.uri} {self.version}"

        content_length_value = str(len(self._body_bytes))

        seen_norms: set[str] = set()
        deduped: list[tuple[str, str]] = []
        for k, v in self.headers._items:
            nk = self.headers._norm(k)
            if nk in self._MULTI_VALUE_HEADERS:
                deduped.append((k, v))
            elif nk == "content-length":
                if "content-length" not in seen_norms:
                    seen_norms.add("content-length")
                    deduped.append((_canonical_header_name("Content-Length"), content_length_value))
            elif nk not in seen_norms:
                seen_norms.add(nk)
                deduped.append((k, v))

        if "content-length" not in seen_norms:
            deduped.append((_canonical_header_name("Content-Length"), content_length_value))

        header_lines = [f"{k}: {v}" for k, v in deduped]
        headers_str = "\r\n".join(header_lines)
        header_part = f"{first_line}\r\n{headers_str}\r\n\r\n" if headers_str else f"{first_line}\r\n\r\n"

        return header_part.encode('utf-8') + self._body_bytes

    def __str__(self):
        try:
            return self.to_bytes().decode('utf-8')
        except UnicodeDecodeError:
            return f"<{self.method or self.status_code} SIP Message with binary body>"