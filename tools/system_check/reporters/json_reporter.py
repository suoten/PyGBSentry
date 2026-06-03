from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, date
from enum import Enum
from typing import Any

from tools.system_check.shared.models import FullCheckReport
from tools.system_check.shared.sanitizer import Sanitizer


class JSONReporter:
    @classmethod
    def render(cls, report: FullCheckReport, sanitize: bool = True) -> str:
        data = cls._to_dict(report)
        if sanitize:
            data = Sanitizer.sanitize_dict(data)
        return json.dumps(data, indent=2, ensure_ascii=False, default=cls._json_default)

    @classmethod
    def _to_dict(cls, obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if is_dataclass(obj):
            result = {}
            for field_name in obj.__dataclass_fields__:
                val = getattr(obj, field_name)
                result[field_name] = cls._to_dict(val)
            return result
        if isinstance(obj, dict):
            return {k: cls._to_dict(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [cls._to_dict(item) for item in obj]
        if isinstance(obj, (str, int, float, bool)):
            return obj
        return str(obj)

    @classmethod
    def _json_default(cls, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return str(obj)


from pathlib import Path
