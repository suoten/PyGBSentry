from __future__ import annotations

from typing import Optional

PYDANTIC_TO_TS: dict[str, str] = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "datetime": "string",
    "date": "string",
    "time": "string",
    "timedelta": "number",
    "UUID": "string",
    "Any": "unknown",
    "bytes": "ArrayBuffer",
    "Decimal": "string",
    "EmailStr": "string",
    "HttpUrl": "string",
    "IPvAnyAddress": "string",
    "PathType": "string",
}

COLLECTION_MAP: dict[str, tuple[str, str]] = {
    "List": ("Array", "[]"),
    "Sequence": ("Array", "[]"),
    "Set": ("Array", "[]"),
    "Tuple": ("[", "]"),
    "Dict": ("Record", "{}"),
    "Mapping": ("Record", "{}"),
}


class TypeMapper:
    @classmethod
    def map(cls, pydantic_type: str) -> str:
        pydantic_type = pydantic_type.strip()

        if pydantic_type.startswith("Optional["):
            inner = pydantic_type[len("Optional["):-1].strip()
            inner_ts = cls.map(inner)
            return f"{inner_ts} | null"

        if pydantic_type.startswith("Union["):
            inner = pydantic_type[len("Union["):-1].strip()
            parts = [p.strip() for p in inner.split(",")]
            ts_parts = [cls.map(p) for p in parts if p != "None"]
            if "None" in parts:
                return " | ".join(ts_parts) + " | null"
            return " | ".join(ts_parts)

        for py_prefix, (ts_prefix, ts_suffix) in COLLECTION_MAP.items():
            if pydantic_type.startswith(f"{py_prefix}["):
                inner = pydantic_type[len(py_prefix) + 1:-1].strip()
                if py_prefix in ("Dict", "Mapping"):
                    parts = [p.strip() for p in inner.split(",", 1)]
                    if len(parts) == 2:
                        key_ts = cls.map(parts[0])
                        val_ts = cls.map(parts[1])
                        return f"Record<{key_ts}, {val_ts}>"
                inner_ts = cls.map(inner)
                return f"Array<{inner_ts}>"

        if pydantic_type in PYDANTIC_TO_TS:
            return PYDANTIC_TO_TS[pydantic_type]

        return pydantic_type

    @classmethod
    def is_compatible(cls, pydantic_type: str, ts_type: str) -> bool:
        mapped = cls.map(pydantic_type)
        if mapped == ts_type:
            return True
        if ts_type.endswith(" | null") and mapped.endswith(" | null"):
            return mapped.rstrip(" | null") == ts_type.rstrip(" | null")
        if ts_type == "any" or ts_type == "unknown":
            return True
        return False
