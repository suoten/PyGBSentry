"""XML utilities for GB28181 SIP message bodies.

Uses defusedxml to prevent XXE attacks. Provides namespace-agnostic helpers
that match the GB28181 catalog/notification XML schemas.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Union

from defusedxml import ElementTree as ET

logger = logging.getLogger(__name__)

# FIX [2026-07-22 P0]: XML prolog encoding 声明正则，用于按声明编码解码 bytes
_XML_ENCODING_RE = re.compile(
    r'<\?xml[^>]+encoding=["\']([\w-]+)["\']', re.IGNORECASE
)


def _decode_bytes_safely(data: bytes) -> str:
    """按 XML prolog 声明编码解码 bytes，失败则回退 UTF-8/GBK。

    GB28181 设备常发送 GB2312 编码的 XML（声明 encoding="GB2312"）。
    若用 UTF-8 解码会导致中文字符乱码，进而 parse_xml 失败。
    """
    # 1) 检测前 4 字节 BOM
    if data.startswith(b"\xef\xbb\xbf"):
        # UTF-8 BOM
        try:
            return data[3:].decode("utf-8", errors="replace")
        except Exception:
            pass
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        # UTF-16 BOM
        try:
            return data.decode("utf-16", errors="replace")
        except Exception:
            pass

    # 2) 按 XML prolog 声明编码解码
    try:
        head = data[:200].decode("ascii", errors="ignore")
        m = _XML_ENCODING_RE.search(head)
        if m:
            declared = m.group(1).lower()
            # GB2312 的超集是 GBK
            enc = "gbk" if declared in ("gb2312", "gbk", "gb18030") else declared
            try:
                return data.decode(enc, errors="replace")
            except (LookupError, UnicodeDecodeError):
                pass
    except Exception:
        pass

    # 3) 回退：先尝试 UTF-8，再尝试 GBK
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("gbk", errors="replace")
        except Exception:
            return data.decode("utf-8", errors="replace")


def parse_xml(xml_str: Union[str, bytes, None]) -> Optional[ET.Element]:
    """Safely parse an XML string into an Element; return None on failure.

    Handles common GB28181 encoding quirks:
      - UTF-8/UTF-16 BOM 头剥离
      - GB2312/GBK 编码（按 XML prolog 声明解码）
      - null 字节清除
      - 多种编码回退

    解析失败时记录原始 XML 内容（截断到 2000 字符）便于排查。
    """
    if not xml_str:
        return None
    try:
        if isinstance(xml_str, bytes):
            xml_str = _decode_bytes_safely(xml_str)

        # 清除 null 字节（部分设备在 body 中混入 \0）
        xml_str = xml_str.replace("\0", "")

        # 清除多种 BOM（UTF-8 BOM \ufeff, UTF-16 BE/LE BOM）
        while xml_str and xml_str[0] in ("\ufeff", "\ufffe"):
            xml_str = xml_str[1:]

        # 去除前后空白
        xml_str = xml_str.strip()

        if not xml_str:
            return None

        return ET.fromstring(xml_str)
    except Exception as e:
        # FIX [2026-07-22 P0]: 解析失败时记录原始 XML 内容（截断到 2000 字符）
        # 便于排查设备返回的非法 XML（如包含未转义特殊字符、不完整标签等）
        _orig_snippet = ""
        try:
            if isinstance(xml_str, bytes):
                _orig_snippet = xml_str.decode("utf-8", errors="replace")[:2000]
            else:
                _orig_snippet = str(xml_str)[:2000]
        except Exception:
            _orig_snippet = "(failed to extract original XML)"
        logger.error(
            f"XML Parse Error: {e} | original_xml_snippet=[{_orig_snippet}]"
        )
        return None


def get_xml_text(element: Optional[ET.Element], tag: str, default: str = "") -> str:
    """Return the text of the first ``element/tag`` child, or ``default``."""
    if element is None:
        return default
    node = element.find(tag)
    return node.text if node is not None and node.text is not None else default


def find_child(element: Optional[ET.Element], tag: str) -> Optional[ET.Element]:
    """Find the first direct or nested child with the given local tag name."""
    if element is None:
        return None
    # Fast path: exact match (most GB28181 bodies are unnamespaced).
    node = element.find(tag)
    if node is not None:
        return node
    # Namespace-agnostic fallback: match by local name.
    for child in element.iter():
        if local_name(child.tag) == tag:
            return child
    return None


def find_children(element: Optional[ET.Element], tag: str) -> list:
    """Find all children (nested) whose local tag name equals ``tag``."""
    if element is None:
        return []
    return [child for child in element.iter() if local_name(child.tag) == tag]


def local_name(tag: str) -> str:
    """Strip the XML namespace prefix from a tag, e.g. ``{ns}Item`` -> ``Item``."""
    if not tag:
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag
