from defusedxml import ElementTree as ET
from typing import Optional
from xml.etree.ElementTree import Element
from loguru import logger

def parse_xml(xml_str: str) -> Optional[Element]:
    """
    Safely parse XML string using defusedxml to prevent XXE.
    Returns the root element or None if parsing fails.
    """
    if not xml_str:
        return None
    try:
        # Handle common encoding issues in GB28181
        if isinstance(xml_str, bytes):
            try:
                xml_str = xml_str.decode('utf-8')
            except UnicodeDecodeError:
                xml_str = xml_str.decode('gb2312', errors='replace')

        # Remove any leading/trailing whitespace or null bytes
        xml_str = xml_str.strip().replace('\0', '')

        return ET.fromstring(xml_str)
    except Exception as e:
        logger.error(f"XML Parse Error: {e}")
        return None

def get_xml_text(element: Optional[Element], tag: str, default: str = "") -> str:
    """
    Helper to get text from an XML element tag safely.
    """
    if element is None:
        return default
    node = find_child(element, tag)
    return node.text if node is not None and node.text is not None else default


def local_name(tag_name: str) -> str:
    """
    Convert namespaced tag like {ns}Tag to Tag.
    """
    if not tag_name:
        return ""
    if "}" in tag_name:
        return tag_name.split("}", 1)[1]
    if ":" in tag_name:
        return tag_name.split(":", 1)[1]
    return tag_name


def find_child(element: Optional[Element], tag: str) -> Optional[Element]:
    """
    Find first direct child by tag name, namespace-insensitive.
    """
    if element is None:
        return None
    for child in list(element):
        if local_name(child.tag) == tag:
            return child
    return element.find(tag)


def find_children(element: Optional[Element], tag: str) -> list[Element]:
    """
    Find all direct children by tag name, namespace-insensitive.
    """
    if element is None:
        return []
    results = [child for child in list(element) if local_name(child.tag) == tag]
    if results:
        return results
    return list(element.findall(tag))
