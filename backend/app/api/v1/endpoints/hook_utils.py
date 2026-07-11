"""ZLM Hook 回调工具函数。

提供从 ZLM webhook 数据中提取字段、判断流注册状态的辅助函数。
"""


def extract_first(data: dict | None, keys: tuple[str, ...]) -> str:
    """从字典中按优先级提取第一个非空值。

    ZLM 不同版本回调字段名可能不同（如 ``app`` / ``appName``），
    此函数按 keys 顺序尝试提取，返回第一个非空字符串值。

    Args:
        data: ZLM 回调 JSON 数据
        keys: 候选字段名列表

    Returns:
        第一个非空值对应的字符串，未找到时返回空字符串
    """
    if not data or not isinstance(data, dict):
        return ""
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def is_stream_unreg(data: dict | None) -> bool:
    """判断 ZLM 回调是否表示流注销（ unregister ）。

    ZLM ``on_stream_changed`` / ``on_stream_none_reader`` 回调中，
    ``regist`` 字段为 ``false`` 表示流注销，``true`` 表示流注册。
    部分 ZLM 版本使用 ``action`` 字段：``"unregister"`` 表示注销。

    Args:
        data: ZLM 回调 JSON 数据

    Returns:
        True 表示流注销，False 表示流注册
    """
    if not data or not isinstance(data, dict):
        return False
    # ZLM on_stream_changed: regist=false 表示注销
    if "regist" in data:
        return not bool(data["regist"])
    # 部分 ZLM 版本使用 registered 字段（字符串 "0"/"1" 或布尔值）
    if "registered" in data:
        val = data["registered"]
        if isinstance(val, str):
            return val.strip() in ("0", "false", "no", "")
        return not bool(val)
    # 部分 ZLM 版本使用 alive 字段（0/False 表示流已注销）
    if "alive" in data:
        return not bool(data["alive"])
    # 部分 ZLM 版本使用 action 字段
    action = str(data.get("action", "") or "").strip().lower()
    if action in ("unregister", "unreg", "stop", "close"):
        return True
    if action in ("register", "reg", "start", "open"):
        return False
    # 默认认为是注册（regist 字段不存在且无 action 时）
    return False
