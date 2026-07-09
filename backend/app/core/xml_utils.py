"""XML utilities for GB28181 SIP message bodies.

Uses defusedxml to prevent XXE attacks. Provides namespace-agnostic helpers
that match the GB28181 catalog/notification XML schemas.
"""
from __future__ import annotations

import logging
from typing import Optional

from defusedxml import ElementTree as ET

logger = logging.getLogger(__name__)


def parse_xml(xml_str: str) -> Optional[ET.Element]:
    """Safely parse an XML string into an Element; return None on failure.

    Handles common GB28181 encoding quirks (gb2312, null bytes, BOM).
    """
    if not xml_str:
        return None
    try:
        if isinstance(xml_str, bytes):
            try:
                xml_str = xml_str.decode("utf-8")
            except UnicodeDecodeError:
                xml_str = xml_str.decode("gb2312", errors="replace")
        xml_str = xml_str.strip().replace("\0", "")
        # Strip XML declaration / BOM that some devices emit.
        if xml_str.startswith("\ufeff"):
            xml_str = xml_str.lstrip("\ufeff")
        return ET.fromstring(xml_str)
    except Exception as e:
        logger.error(f"XML Parse Error: {e}")
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
