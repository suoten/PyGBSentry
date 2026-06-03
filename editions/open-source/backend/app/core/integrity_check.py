import hashlib
import os

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

def check_integrity(base_dir: str) -> list[str]:
    warnings = []
    core_dir = os.path.join(base_dir, "app", "core")
    svc_dir = os.path.join(base_dir, "app", "services")
    for filename, expected_hash in CRITICAL_FILES.items():
        for search_dir in [core_dir, svc_dir]:
            filepath = os.path.join(search_dir, filename)
            if os.path.exists(filepath):
                if expected_hash and compute_file_hash(filepath) != expected_hash:
                    warnings.append(f"{filename} integrity check failed, possible tampering")
                break
    return warnings
