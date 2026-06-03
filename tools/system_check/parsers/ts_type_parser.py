from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


class TsTypeParser:
    _INTERFACE_RE = re.compile(r"(?:export\s+)?interface\s+(\w+)\s*(?:extends\s+\w+\s*)?\{", re.MULTILINE)
    _TYPE_RE = re.compile(r"(?:export\s+)?type\s+(\w+)\s*=", re.MULTILINE)
    _FIELD_RE = re.compile(r"(\w+)(\?)?\s*:\s*([^;]+);")
    _ENUM_RE = re.compile(r"(?:export\s+)?enum\s+(\w+)\s*\{", re.MULTILINE)

    @classmethod
    def parse_file(cls, file_path: str | Path) -> dict[str, dict]:
        path = Path(file_path)
        if not path.exists():
            return {}
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        return cls.parse_content(content)

    @classmethod
    def parse_directory(cls, dir_path: str | Path) -> dict[str, dict]:
        directory = Path(dir_path)
        if not directory.exists():
            return {}
        all_types: dict[str, dict] = {}
        for f in directory.rglob("*.ts"):
            if f.name.endswith(".d.ts"):
                continue
            types = cls.parse_file(f)
            all_types.update(types)
        for f in directory.rglob("*.js"):
            types = cls.parse_file(f)
            all_types.update(types)
        return all_types

    @classmethod
    def parse_content(cls, content: str) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for match in cls._INTERFACE_RE.finditer(content):
            name = match.group(1)
            start = match.end()
            body = cls._extract_brace_block(content, start - 1)
            if body:
                fields = cls._parse_fields(body)
                result[name] = {"kind": "interface", "fields": fields, "raw": body}
        for match in cls._TYPE_RE.finditer(content):
            name = match.group(1)
            rest = content[match.end():].strip()
            if rest.startswith("{"):
                body = cls._extract_brace_block(content, match.end())
                if body:
                    fields = cls._parse_fields(body)
                    result[name] = {"kind": "type", "fields": fields, "raw": body}
            else:
                type_def = rest.split(";")[0].strip() if ";" in rest else rest.split("\n")[0].strip()
                result[name] = {"kind": "type_alias", "fields": {}, "type_def": type_def}
        return result

    @classmethod
    def _extract_brace_block(cls, content: str, start: int) -> Optional[str]:
        if start >= len(content) or content[start] != "{":
            return None
        depth = 0
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    return content[start + 1 : i]
        return None

    @classmethod
    def _parse_fields(cls, body: str) -> dict[str, dict]:
        fields: dict[str, dict] = {}
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("/*"):
                continue
            match = cls._FIELD_RE.search(line)
            if match:
                name = match.group(1)
                optional = match.group(2) is not None
                type_str = match.group(3).strip()
                fields[name] = {"type": type_str, "optional": optional}
        return fields
