import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    ("app/sip/catalog.py", "handle_catalog_response"),
    ("app/sip/handlers.py", "init_handlers"),
    ("app/sip/commander.py", "SipCommander"),
    ("app/sip/ptz.py", "SipPtz"),
    ("app/services/platform_service.py", "PlatformService"),
]


def main() -> int:
    failed = False
    for relative_path, symbol in CHECKS:
        file_path = PROJECT_ROOT / relative_path
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except Exception as e:
            failed = True
            print(f"[FAIL] parse {relative_path}: {e}")
            continue

        found = False
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
                found = True
                break

        if not found:
            failed = True
            print(f"[FAIL] {relative_path} missing symbol: {symbol}")
            continue

        print(f"[OK] {relative_path}:{symbol}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
