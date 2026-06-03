from __future__ import annotations


def extract_first(data: dict | None, keys: tuple[str, ...]) -> str:
    if not isinstance(data, dict):
        return ""
    for k in keys:
        if k not in data:
            continue
        v = data.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def is_stream_unreg(data: dict | None) -> bool:
    if not isinstance(data, dict):
        return False
    for k in ("regist", "registered", "register", "is_regist", "is_registered"):
        if k in data:
            v = data.get(k)
            if isinstance(v, bool):
                return v is False
            try:
                return int(v) == 0
            except Exception:
                return str(v).strip().lower() in {"false", "0", "no"}
    for k in ("alive", "online"):
        if k in data:
            try:
                return int(data.get(k)) == 0
            except Exception:
                return str(data.get(k)).strip().lower() in {"false", "0", "no"}
    return False

