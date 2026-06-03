#!/usr/bin/env python3
"""自动修复 except ...: pass 异常吞没问题
处理两种模式:
1. 同行: except XXX: pass
2. 跨行: except XXX:\n    pass
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LOGGER_IMPORT_RE = re.compile(r"from\s+loguru\s+import\s+logger")
LOGGER_USE_RE = re.compile(r"logger\.\w+\(")
INTENTIONAL_RE = re.compile(r"#\s*intentional|#\s*noqa|#\s?type:\s*ignore")

CANCELLED_EXCEPTIONS = {
    "asyncio.CancelledError",
    "asyncio.TimeoutError",
    "asyncio.CancelledError, asyncio.TimeoutError",
    "asyncio.TimeoutError, asyncio.CancelledError",
    "asyncio.CancelledError, asyncio.TimeoutError, Exception",
}

def has_logger_import(content: str) -> bool:
    return bool(LOGGER_IMPORT_RE.search(content))

def inject_logger_import(content: str) -> str:
    lines = content.splitlines(keepends=True)
    insert_pos = 0
    in_future = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("from __future__"):
            in_future = True
            insert_pos = i + 1
        elif in_future and stripped and not stripped.startswith("from __future__"):
            break
        elif stripped.startswith("import ") or stripped.startswith("from "):
            insert_pos = i + 1
    import_line = "from loguru import logger\n"
    lines.insert(insert_pos, import_line)
    return "".join(lines)

def is_cancelled_exception(exc_type: str) -> bool:
    clean = exc_type.strip().rstrip(":").strip()
    for cancelled in CANCELLED_EXCEPTIONS:
        if clean == cancelled:
            return True
    return False

def fix_file(file_path: Path, dry_run: bool = False) -> tuple[int, bool]:
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, False

    lines = content.splitlines()
    original_lines = list(lines)
    fix_count = 0
    needs_logger = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 检查同行模式: except XXX: pass
        same_line_match = re.match(r'^(\s*)(except\s+(.+?)\s*(?:as\s+(\w+))?\s*:\s*)pass\s*$', stripped)
        if same_line_match:
            indent = same_line_match.group(1)
            exc_part = same_line_match.group(2).rstrip()
            exc_type = same_line_match.group(3)
            var_name = same_line_match.group(4)

            if INTENTIONAL_RE.search(stripped):
                i += 1
                continue

            if is_cancelled_exception(exc_type):
                new_line = f"{indent}{exc_part}"
                lines[i] = new_line
                lines.insert(i + 1, f"{indent}    pass  # intentional: asyncio cancellation")
                fix_count += 1
                needs_logger = True
                i += 2
                continue

            if var_name:
                new_line = f"{indent}{exc_part}"
                lines[i] = new_line
                lines.insert(i + 1, f'{indent}    logger.warning(f"{exc_type}: {{{var_name}}}")')
            else:
                new_line = f"{indent}{exc_part}"
                lines[i] = new_line
                lines.insert(i + 1, f'{indent}    logger.warning("{exc_type} occurred")')

            fix_count += 1
            needs_logger = True
            i += 2
            continue

        # 检查跨行模式: except XXX:\n    pass
        cross_line_match = re.match(r'^(\s*)(except\s+(.+?)\s*(?:as\s+(\w+))?\s*:)\s*$', stripped)
        if cross_line_match and i + 1 < len(lines):
            next_stripped = lines[i + 1].strip()
            if next_stripped == "pass":
                indent = cross_line_match.group(1)
                exc_part = cross_line_match.group(2).rstrip().rstrip(":")
                exc_type = cross_line_match.group(3)
                var_name = cross_line_match.group(4)

                # 检查是否有intentional标记
                is_intentional = False
                if INTENTIONAL_RE.search(stripped):
                    is_intentional = True
                if i + 2 < len(lines) and INTENTIONAL_RE.search(lines[i + 2].strip()):
                    is_intentional = True

                if is_intentional:
                    i += 2
                    continue

                if is_cancelled_exception(exc_type):
                    lines[i + 1] = f"{indent}    pass  # intentional: asyncio cancellation"
                    fix_count += 1
                    needs_logger = True
                    i += 2
                    continue

                if var_name:
                    lines[i + 1] = f'{indent}    logger.warning(f"{exc_type}: {{{var_name}}}")'
                else:
                    lines[i + 1] = f'{indent}    logger.warning("{exc_type} occurred")'

                fix_count += 1
                needs_logger = True
                i += 2
                continue

        i += 1

    if fix_count == 0:
        return 0, False

    new_content = "\n".join(lines)
    if not content.endswith("\n") and original_lines:
        pass

    if needs_logger and not has_logger_import(new_content):
        new_content = inject_logger_import(new_content)

    original_content = "\n".join(original_lines)
    if new_content != original_content and not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return fix_count, needs_logger

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    targets = [
        Path("E:/硕腾网络/PyGBSentry/PyGBSentry/editions/open-source/backend/app"),
        Path("E:/硕腾网络/PyGBSentry/PyGBSentry/editions/server/backend/app"),
    ]

    total_fixed = 0
    total_files = 0

    for target in targets:
        if not target.exists():
            continue
        edition = "open-source" if "open-source" in str(target) else "server"
        print(f"\n扫描: {edition}")
        for py_file in sorted(target.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            count, injected = fix_file(py_file, dry_run=dry_run)
            if count > 0:
                total_fixed += count
                total_files += 1
                rel = str(py_file).replace("E:/硕腾网络/PyGBSentry/PyGBSentry/", "")
                status = "DRY-RUN" if dry_run else "FIXED"
                logger_status = " +logger" if injected else ""
                print(f"  [{status}] {rel}: {count}处{logger_status}")

    print(f"\n{'='*60}")
    print(f"总修复: {total_fixed}处异常吞没, 涉及{total_files}个文件")
    if dry_run:
        print("(DRY-RUN模式，未实际修改文件)")

if __name__ == "__main__":
    main()
