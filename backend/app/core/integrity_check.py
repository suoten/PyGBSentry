import hashlib
import os
import json
from pathlib import Path

_CACHE_FILE = Path(__file__).resolve().parent / ".integrity_hashes.json"

CRITICAL_FILES = {
    "plugin_manager.py": None,
    "license_service.py": None,
}


def compute_file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except (OSError, IOError):
        return ""
    return h.hexdigest()


def _load_cached_hashes() -> dict[str, str]:
    try:
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cached_hashes(hashes: dict[str, str]) -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=2)
    except Exception:
        pass


def build_baseline(base_dir: str) -> dict[str, str]:
    """Compute and cache hashes for all critical files."""
    hashes: dict[str, str] = {}
    core_dir = os.path.join(base_dir, "app", "core")
    svc_dir = os.path.join(base_dir, "app", "services")
    for filename in CRITICAL_FILES:
        for search_dir in [core_dir, svc_dir]:
            filepath = os.path.join(search_dir, filename)
            if os.path.exists(filepath):
                h = compute_file_hash(filepath)
                if h:
                    hashes[filename] = h
                break
    _save_cached_hashes(hashes)
    return hashes


def check_integrity(base_dir: str) -> list[str]:
    warnings: list[str] = []
    cached = _load_cached_hashes()
    if not cached:
        # First run: build baseline silently
        build_baseline(base_dir)
        return warnings
    core_dir = os.path.join(base_dir, "app", "core")
    svc_dir = os.path.join(base_dir, "app", "services")
    for filename, expected_hash in cached.items():
        for search_dir in [core_dir, svc_dir]:
            filepath = os.path.join(search_dir, filename)
            if os.path.exists(filepath):
                current_hash = compute_file_hash(filepath)
                if current_hash and current_hash != expected_hash:
                    warnings.append(f"{filename} integrity check failed, possible tampering")
                break
    return warnings
