"""
插件安全扫描模块（从服务器版移植）

在安装/升级插件 ZIP 包时，扫描 .py 源码和依赖配置文件中的危险用法，
防止恶意插件危害宿主系统。

扫描规则覆盖 8 大类 33+ 条模式：
- dangerous_call: subprocess/os.system/os.popen/eval/exec/__import__/compile/open_write/
                  shutil.rmtree/os.remove/sys.exit/signal/type_metaclass/object_newstyle/
                  __builtins__/getattr_chain/setattr_dynamic/memoryview/buffer/bytearray/
                  eval_with_globals/exec_with_globals/compile_mode/__import__dynamic
- native_api: ctypes/multiprocessing/cffi/winreg/importlib
- deserialization: pickle.loads/pickle.load
- network_lib: requests/httpx/urllib/socket/paramiko
- dependency_source_risk: git+ 依赖源
- dependency_index_risk: 自定义索引源
"""
import os
import posixpath
import re
import zipfile

from app.core.config import settings
from loguru import logger



_PLUGIN_SECURITY_SCAN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("dangerous_call:subprocess", re.compile(r"\bsubprocess\b")),
    ("dangerous_call:os.system", re.compile(r"os\.system\s*\(")),
    ("dangerous_call:os.popen", re.compile(r"os\.popen\s*\(")),
    ("dangerous_call:eval", re.compile(r"\beval\s*\(")),
    ("dangerous_call:exec", re.compile(r"\bexec\s*\(")),
    ("dangerous_call:__import__", re.compile(r"__import__\s*\(")),
    ("dangerous_call:compile", re.compile(r"\bcompile\s*\(")),
    ("dangerous_call:open_write", re.compile(r"\bopen\s*\([^)]*[\"']w")),
    ("dangerous_call:shutil.rmtree", re.compile(r"shutil\.rmtree\s*\(")),
    ("dangerous_call:os.remove", re.compile(r"os\.remove\s*\(")),
    ("dangerous_call:sys.exit", re.compile(r"sys\.exit\s*\(")),
    ("dangerous_call:signal", re.compile(r"\bimport\s+signal\b|\bfrom\s+signal\b")),
    ("dangerous_call:type_metaclass", re.compile(r"\btype\s*\([^)]*\)\s*(?![\s]*[,\)]?\s*(?:globals|locals|vars|bases))")),
    ("dangerous_call:object_newstyle", re.compile(r"object\s*\.\s*(?:__subclasses__|__bases__|__mro__|__dict__)")),
    ("dangerous_call:__builtins__", re.compile(r"__builtins__")),
    ("dangerous_call:getattr_chain", re.compile(r"getattr\s*\(\s*[^,]+,\s*['\"](?:__class__|__bases__|__mro__|__globals__|__code__|__closure__|__func__|__self__)")),
    ("dangerous_call:setattr_dynamic", re.compile(r"setattr\s*\(\s*[^,]+,\s*['\"][^'\"]+['\"],\s*[^)]+\)")),
    ("dangerous_call:memoryview", re.compile(r"\bmemoryview\s*\(")),
    ("dangerous_call:buffer", re.compile(r"\bbuffer\s*\(")),
    ("dangerous_call:bytearray", re.compile(r"\bbytearray\s*\(")),
    ("dangerous_call:eval_with_globals", re.compile(r"eval\s*\([^)]*globals")),
    ("dangerous_call:exec_with_globals", re.compile(r"exec\s*\([^)]*globals")),
    ("dangerous_call:compile_mode", re.compile(r"compile\s*\([^)]*['\"]exec")),
    ("dangerous_call:__import__dynamic", re.compile(r"__import__\s*\([^)]*\{|\__import__\s*\([^)]*\[")),
    ("native_api:ctypes", re.compile(r"\bctypes\b")),
    ("native_api:multiprocessing", re.compile(r"\bmultiprocessing\b")),
    ("native_api:cffi", re.compile(r"\bimport\s+cffi\b|\bfrom\s+cffi\b")),
    ("native_api:winreg", re.compile(r"\bimport\s+winreg\b|\bfrom\s+winreg\b")),
    ("native_api:importlib", re.compile(r"\bimport\s+importlib\b|\bfrom\s+importlib\b")),
    ("deserialization:pickle.loads", re.compile(r"pickle\.loads\s*\(")),
    ("deserialization:pickle.load", re.compile(r"pickle\.load\s*\(")),
    ("network_lib:requests", re.compile(r"\bimport\s+requests\b|\bfrom\s+requests\b")),
    ("network_lib:httpx", re.compile(r"\bimport\s+httpx\b|\bfrom\s+httpx\b")),
    ("network_lib:urllib", re.compile(r"\bimport\s+urllib\b|\bfrom\s+urllib\b")),
    ("network_lib:socket", re.compile(r"\bimport\s+socket\b|\bfrom\s+socket\b")),
    ("network_lib:paramiko", re.compile(r"\bimport\s+paramiko\b|\bfrom\s+paramiko\b")),
]


def scan_zip_for_security_risks(zip_ref: zipfile.ZipFile, file_list: list[str]) -> list[str]:
    """
    扫描 ZIP 包中的 .py 文件和依赖配置文件，返回安全风险命中列表。
    受 PLUGIN_SECURITY_SCAN_ENABLED 开关控制。
    """
    # FIX: [2026-07-16 P1] 原默认 PLUGIN_SECURITY_SCAN_ENABLED=False，
    # 导致插件 ZIP 包安装时不执行任何安全扫描（subprocess/eval/pickle/ctypes 等 33 条规则），
    # 超级管理员被钓鱼即可实现 RCE。改为默认开启。
    if not settings.PLUGIN_SECURITY_SCAN_ENABLED:
        return []

    max_files = settings.PLUGIN_SECURITY_SCAN_MAX_FILE_COUNT
    max_bytes = settings.PLUGIN_SECURITY_SCAN_MAX_FILE_BYTES
    max_hits = settings.PLUGIN_SECURITY_SCAN_MAX_HITS
    if max_files <= 0 or max_bytes <= 0 or max_hits <= 0:
        return []

    py_files = [n for n in (file_list or []) if isinstance(n, str) and n.endswith(".py")]
    if not py_files:
        return []

    hits: list[str] = []
    for idx, name in enumerate(py_files[:max_files]):
        try:
            with zip_ref.open(name) as f:
                raw = f.read(max_bytes)
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue

        for label, pat in _PLUGIN_SECURITY_SCAN_PATTERNS:
            if pat.search(text):
                hits.append(f"{name}: {label}")
                if len(hits) >= max_hits:
                    return hits
                break

    config_files = [
        n
        for n in (file_list or [])
        if isinstance(n, str)
        and (
            n.lower().endswith("pyproject.toml")
            or n.lower().endswith("setup.cfg")
            or n.lower().endswith("setup.py")
        )
    ]
    for name in config_files[:min(max_files, 10)]:
        if len(hits) >= max_hits:
            return hits
        try:
            with zip_ref.open(name) as f:
                raw = f.read(max_bytes)
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue

        for line in text.splitlines():
            s = str(line).strip()
            if not s or s.startswith("#"):
                continue
            if "git+" in s or s.startswith("git+"):
                hits.append(f"{name}: dependency_source_risk: {s[:80]}")
            elif "--extra-index-url" in s or s.startswith("--extra-index-url"):
                hits.append(f"{name}: dependency_index_risk: {s[:80]}")
            elif "--index-url" in s or s.startswith("--index-url"):
                hits.append(f"{name}: dependency_index_risk: {s[:80]}")
            elif s.startswith("-r ") or s.startswith("--requirement"):
                hits.append(f"{name}: dependency_ref_risk: {s[:80]}")
            elif s.startswith("-c ") or s.startswith("--constraint"):
                hits.append(f"{name}: dependency_constraint_risk: {s[:80]}")
            else:
                continue
            if len(hits) >= max_hits:
                return hits

    def _normalize_zip_path(p: str) -> str:
        return str(p or "").replace("\\", "/").lstrip("/")

    def _resolve_requirements_include(base_req_path: str, include_spec: str) -> str | None:
        include_spec = str(include_spec or "").strip().strip('"').strip("'")
        if not include_spec:
            return None
        spec = _normalize_zip_path(include_spec)
        if spec.startswith("/"):
            spec = spec.lstrip("/")
        base_dir = _normalize_zip_path(base_req_path)
        if "/" in base_dir:
            base_dir = base_dir.rsplit("/", 1)[0]
        else:
            base_dir = ""
        resolved = spec if not base_dir else f"{base_dir}/{spec}"
        resolved = posixpath.normpath(resolved).replace("\\", "/").lstrip("/")
        if resolved.startswith("../") or resolved == ".." or resolved.startswith(".."):
            return None
        return resolved

    def _scan_requirements_file(req_path: str, *, scanned: set[str], depth: int) -> None:
        nonlocal hits
        if len(hits) >= max_hits:
            return
        if not req_path or req_path in scanned:
            return
        if len(scanned) >= min(max_files, 10):
            return
        if depth > 8:
            return
        scanned.add(req_path)
        try:
            with zip_ref.open(req_path) as f:
                raw = f.read(max_bytes)
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            return

        for line in text.splitlines():
            s = str(line).strip()
            if not s or s.startswith("#"):
                continue
            if "git+" in s or s.startswith("git+"):
                hits.append(f"{req_path}: dependency_source_risk: {s[:80]}")
            elif "--extra-index-url" in s or s.startswith("--extra-index-url"):
                hits.append(f"{req_path}: dependency_index_risk: {s[:80]}")
            elif "--index-url" in s or s.startswith("--index-url"):
                hits.append(f"{req_path}: dependency_index_risk: {s[:80]}")
            elif s.startswith("-r ") or s.startswith("--requirement"):
                hits.append(f"{req_path}: dependency_ref_risk: {s[:80]}")
                try:
                    inc = ""
                    if s.startswith("-r "):
                        inc = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else ""
                    elif "--requirement=" in s:
                        inc = s.split("=", 1)[1]
                    else:
                        inc = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else ""
                    resolved = _resolve_requirements_include(req_path, inc)
                    if resolved:
                        _scan_requirements_file(resolved, scanned=scanned, depth=depth + 1)
                except Exception as e:
                    logger.warning(f"Error: {e}")
            elif s.startswith("-c ") or s.startswith("--constraint"):
                hits.append(f"{req_path}: dependency_constraint_risk: {s[:80]}")
                try:
                    inc = ""
                    if s.startswith("-c "):
                        inc = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else ""
                    elif "--constraint=" in s:
                        inc = s.split("=", 1)[1]
                    else:
                        inc = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else ""
                    resolved = _resolve_requirements_include(req_path, inc)
                    if resolved:
                        _scan_requirements_file(resolved, scanned=scanned, depth=depth + 1)
                except Exception as e:
                    logger.warning(f"Error: {e}")
            if len(hits) >= max_hits:
                return

    req_files = [
        n
        for n in (file_list or [])
        if isinstance(n, str) and n.lower().endswith("requirements.txt")
    ]
    req_files.extend(
        [
            n
            for n in (file_list or [])
            if isinstance(n, str)
            and n.lower().endswith(".txt")
            and (os.path.basename(n).lower().startswith("requirements") or os.path.basename(n).lower().startswith("constraints"))
            and str(n).lower() not in {x.lower() for x in req_files}
        ]
    )
    scanned: set[str] = set()
    for root in req_files[:min(max_files, 10)]:
        _scan_requirements_file(_normalize_zip_path(root), scanned=scanned, depth=0)
        if len(hits) >= max_hits:
            return hits

    return hits


def build_security_report(security_hits: list[str]) -> dict:
    """将安全扫描命中列表构建为结构化报告。"""
    if not security_hits:
        return {"hits": [], "summary": {}, "groups": {}}

    severity_rank = {
        "dangerous_call": "high",
        "native_api": "high",
        "deserialization": "high",
        "dependency_source_risk": "medium",
        "dependency_index_risk": "medium",
        "dependency_ref_risk": "medium",
        "dependency_constraint_risk": "medium",
        "network_lib": "medium",
    }

    def _severity_for(kind: str) -> str:
        return severity_rank.get(kind, "low")

    groups: dict[str, list[dict]] = {}
    summary: dict[str, int] = {}
    parsed_hits: list[dict] = []

    for raw in security_hits:
        if not isinstance(raw, str) or not raw.strip():
            continue
        if ": " not in raw:
            continue
        file_part, rest = raw.split(": ", 1)
        file_part = str(file_part).strip()
        rest = str(rest).strip()
        item: dict = {"file": file_part, "raw": raw}
        group_kind = "unknown"
        if rest.startswith("dependency_") and ":" in rest:
            dep_kind, dep_detail = rest.split(":", 1)
            dep_kind = dep_kind.strip()
            dep_detail = dep_detail.strip()
            group_kind = dep_kind
            item.update({"kind": dep_kind, "detail": dep_detail})
        elif ":" in rest:
            kind, detail = rest.split(":", 1)
            kind = kind.strip()
            detail = detail.strip()
            group_kind = kind
            item.update({"kind": kind, "detail": detail})
        else:
            item.update({"kind": rest, "detail": ""})
            group_kind = rest
        severity = _severity_for(group_kind)
        item["severity"] = severity
        parsed_hits.append(item)
        summary[group_kind] = summary.get(group_kind, 0) + 1
        groups.setdefault(group_kind, []).append({"file": item["file"], "detail": item.get("detail", ""), "severity": severity})

    return {"hits": security_hits, "summary": summary, "groups": groups}