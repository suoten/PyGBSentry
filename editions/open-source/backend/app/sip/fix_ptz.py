import os

BASE = r'E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip'

# Fix ptz.py encoding - read as bytes, fix broken sequences, write back
filepath = os.path.join(BASE, 'ptz.py')
with open(filepath, 'rb') as f:
    raw = f.read()

# Replace broken UTF-8 sequences with ASCII equivalents
# The PowerShell replacement corrupted Chinese characters
# Replace the broken docstrings with English equivalents
content = raw.decode('utf-8', errors='replace')

# Find all broken replacement characters and fix the docstrings
fixes = [
    ('国标预置位设置：A5 0F 01 81 00 [preset_id] 00 + 校验。preset_id 1-255\ufffd?""', 
     'GB preset set: A5 0F 01 81 00 [preset_id] 00 + checksum. preset_id 1-255."""'),
    ('国标预置位删除：A5 0F 01 81 00 [preset_id] 01 + 校验。preset_id 1-255\ufffd?""',
     'GB preset delete: A5 0F 01 81 00 [preset_id] 01 + checksum. preset_id 1-255."""'),
    ('国标预置位调用：A5 0F 01 81 00 [preset_id] 02 + 校验。preset_id 1-255\ufffd?""',
     'GB preset goto: A5 0F 01 81 00 [preset_id] 02 + checksum. preset_id 1-255."""'),
    ('3D 放大/定位 (DragZoom - GB/T 28181\ufffd??2022 & 2016 扩展)',
     'DragZoom - GB/T 28181-2022 & 2016 extension'),
    ('GB/T 28181\ufffd??2022 绝对云台控制 (Absolute PTZ)',
     'GB/T 28181-2022 Absolute PTZ'),
]

for old, new in fixes:
    if old in content:
        content = content.replace(old, new)
        print(f'Fixed: {old[:30]}...')

# Also replace any remaining replacement characters in docstrings
import re
# Find lines with \ufffd (replacement character) and replace the whole docstring
lines = content.split('\n')
for i, line in enumerate(lines):
    if '\ufffd' in line and '"""' in line:
        # This is a corrupted docstring, replace with a simple English one
        indent = len(line) - len(line.lstrip())
        lines[i] = ' ' * indent + '"""."""'
        print(f'Replaced corrupted docstring at line {i+1}')

content = '\n'.join(lines)

with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print('Fixed ptz.py')
