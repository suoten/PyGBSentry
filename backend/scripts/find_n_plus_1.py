"""扫描可能存在 N+1 查询的代码模式。
检测：
  1. for ... in ... 循环内执行 db.execute / session.execute
  2. for ... in ... 循环内执行 await db.get / await session.get
"""
import re
import pathlib

app_dir = pathlib.Path('app')
issues = []

for py_file in app_dir.rglob('*.py'):
    if '__pycache__' in str(py_file):
        continue
    try:
        lines = py_file.read_text(encoding='utf-8').splitlines()
    except Exception:
        continue

    in_loop_depth = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 检测 for 循环开始
        if re.match(r'^for\s+\w+\s+in\s+', stripped):
            in_loop_depth = i
            continue
        # 检测循环内是否有 DB 查询
        if in_loop_depth > 0:
            # 检测循环结束（缩进回到循环级别或更浅）
            if i > in_loop_depth + 30:  # 只看循环体前30行
                in_loop_depth = 0
                continue
            if re.search(r'(await\s+)?(db|session|_db|_session)\.(execute|get)\s*\(', stripped):
                issues.append(f"{py_file}:{i}: {stripped}")
                in_loop_depth = 0

if issues:
    print(f"Found {len(issues)} potential N+1 patterns:")
    for issue in issues:
        print(f"  {issue}")
else:
    print("No N+1 patterns found")
