"""
自动修复 except Exception: pass 异常吞没模式。
策略：
  - except Exception: pass → except Exception as e: logger.warning(f"...: {e}")
  - except Exception as e: logger.debug(...) → except Exception as e: logger.warning(...)
  - except asyncio.CancelledError: pass → 保留但加 logger.debug
  - except RuntimeError: pass → except RuntimeError as e: logger.debug(...)
  - except (ValueError, TypeError, ...): pass → 加 logger.debug
  - except (asyncio.CancelledError, asyncio.TimeoutError): pass → 加 logger.debug
"""
import re
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent / "app"

# 需要排除的目录
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}

def fix_file(filepath: Path) -> int:
    """修复单个文件，返回修改的行数。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return 0

    lines = content.splitlines(keepends=True)
    changes = 0
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n\r")
        stripped_no_space = stripped.strip()

        # 模式1: except Exception: pass  (单行)
        if re.match(r'^(\s*)except\s+Exception\s*:\s*pass\s*$', stripped):
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f"{indent}except Exception as _exc:\n")
            new_lines.append(f'{indent}    logger.warning(f"silently_swallowed: {{_exc}}", exc_info=True)\n')
            changes += 1
            i += 1
            continue

        # 模式2: except: pass (裸except)
        if re.match(r'^(\s*)except\s*:\s*pass\s*$', stripped):
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f"{indent}except Exception as _exc:\n")
            new_lines.append(f'{indent}    logger.warning(f"silently_swallowed_bare: {{_exc}}", exc_info=True)\n')
            changes += 1
            i += 1
            continue

        # 模式3: except (SomeError, OtherError): pass
        m = re.match(r'^(\s*)except\s+\(([^)]+)\)\s*:\s*pass\s*$', stripped)
        if m:
            indent = m.group(1)
            exc_types = m.group(2)
            # 如果包含 CancelledError，用 debug 级别
            if "CancelledError" in exc_types:
                new_lines.append(f"{indent}except ({exc_types}) as _exc:\n")
                new_lines.append(f'{indent}    logger.debug(f"cancelled_or_timeout: {{_exc}}")\n')
            else:
                new_lines.append(f"{indent}except ({exc_types}) as _exc:\n")
                new_lines.append(f'{indent}    logger.debug(f"swallowed_specific: {{_exc}}")\n')
            changes += 1
            i += 1
            continue

        # 模式4: except SomeError: pass (单个异常类型)
        m = re.match(r'^(\s*)except\s+(\w+)\s*:\s*pass\s*$', stripped)
        if m:
            indent = m.group(1)
            exc_type = m.group(2)
            if exc_type in ("CancelledError",):
                new_lines.append(f"{indent}except {exc_type} as _exc:\n")
                new_lines.append(f'{indent}    logger.debug(f"cancelled: {{_exc}}")\n')
            elif exc_type in ("ImportError", "ModuleNotFoundError"):
                new_lines.append(f"{indent}except {exc_type} as _exc:\n")
                new_lines.append(f'{indent}    logger.debug(f"import_skipped: {{_exc}}")\n')
            else:
                new_lines.append(f"{indent}except {exc_type} as _exc:\n")
                new_lines.append(f'{indent}    logger.debug(f"swallowed_{exc_type.lower()}: {{_exc}}")\n')
            changes += 1
            i += 1
            continue

        # 模式5: except Exception as e: logger.debug(...) → 升级为 warning
        m = re.match(r'^(\s*)except\s+Exception\s+as\s+\w+\s*:\s*$', stripped)
        if m:
            indent = m.group(1)
            # 检查下一行是否是 logger.debug
            if i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if next_stripped.startswith("logger.debug("):
                    # 替换 logger.debug 为 logger.warning
                    new_lines.append(line)  # 保持 except 行不变
                    next_line = lines[i + 1]
                    next_line = next_line.replace("logger.debug(", "logger.warning(", 1)
                    new_lines.append(next_line)
                    changes += 1
                    i += 2
                    continue

        # 模式6: 多行 except 块中只有 pass
        # except Exception:
        #     pass
        m = re.match(r'^(\s*)except\s+.*:\s*$', stripped)
        if m and i + 1 < len(lines):
            indent = m.group(1)
            next_line = lines[i + 1]
            next_stripped = next_line.strip()
            if next_stripped == "pass":
                # 这是 except ...: \n pass 模式
                # 检查 except 类型
                except_content = stripped_no_space
                if "CancelledError" in except_content:
                    new_lines.append(line)  # 保持 except 行
                    new_lines.append(f'{indent}    logger.debug("task_cancelled")\n')
                elif "ImportError" in except_content or "ModuleNotFoundError" in except_content:
                    new_lines.append(line)
                    new_lines.append(f'{indent}    logger.debug("optional_import_skipped")\n')
                elif "Exception" in except_content:
                    new_lines.append(line)
                    new_lines.append(f'{indent}    logger.warning("silently_swallowed_exception", exc_info=True)\n')
                else:
                    new_lines.append(line)
                    new_lines.append(f'{indent}    logger.debug("swallowed_exception", exc_info=True)\n')
                changes += 1
                i += 2
                continue

        new_lines.append(line)
        i += 1

    if changes > 0:
        filepath.write_text("".join(new_lines), encoding="utf-8")

    return changes


def main():
    total_changes = 0
    files_changed = 0

    for py_file in BACKEND_DIR.rglob("*.py"):
        # 排除目录
        if any(part in EXCLUDE_DIRS for part in py_file.parts):
            continue

        changes = fix_file(py_file)
        if changes > 0:
            files_changed += 1
            total_changes += changes
            print(f"  Fixed {changes:3d} in {py_file.relative_to(BACKEND_DIR)}")

    print(f"\nTotal: {total_changes} fixes in {files_changed} files")


if __name__ == "__main__":
    main()
