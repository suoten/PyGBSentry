import os

BASE = r'E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip'

# Fix all files that were corrupted by PowerShell Set-Content
files_to_fix = ['catalog.py', 'device_control.py', 'commander.py', 'ptz.py']

for fn in files_to_fix:
    fp = os.path.join(BASE, fn)
    with open(fp, 'rb') as f:
        raw = f.read()
    
    content = raw.decode('utf-8', errors='replace')
    
    # Replace corrupted docstrings (containing replacement character \ufffd)
    lines = content.split('\n')
    fixed = 0
    for i, line in enumerate(lines):
        if '\ufffd' in line:
            # Check if this is a docstring line
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if '"""' in stripped:
                # Replace with empty docstring
                lines[i] = ' ' * indent + '"""."""'
                fixed += 1
            else:
                # Just remove the replacement character
                lines[i] = line.replace('\ufffd', '')
                fixed += 1
    
    if fixed > 0:
        content = '\n'.join(lines)
        with open(fp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        print(f'Fixed {fn}: {fixed} corrupted lines')
    else:
        print(f'{fn}: no corruption found')

# Also check cascade.py
fp = os.path.join(BASE, 'cascade.py')
with open(fp, 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8', errors='replace')
lines = content.split('\n')
fixed = 0
for i, line in enumerate(lines):
    if '\ufffd' in line:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if '"""' in stripped:
            lines[i] = ' ' * indent + '"""."""'
            fixed += 1
        else:
            lines[i] = line.replace('\ufffd', '')
            fixed += 1
if fixed > 0:
    content = '\n'.join(lines)
    with open(fp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print(f'Fixed cascade.py: {fixed} corrupted lines')
else:
    print('cascade.py: no corruption found')

# Verify all files compile
import py_compile
all_files = ['catalog.py', 'device_control.py', 'commander.py', 'ptz.py', 'cascade.py']
for fn in all_files:
    fp = os.path.join(BASE, fn)
    try:
        py_compile.compile(fp, doraise=True)
        print(f'{fn}: compiles OK')
    except Exception as e:
        print(f'{fn}: COMPILE ERROR: {e}')
