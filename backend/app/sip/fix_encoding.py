import os

BASE = r'E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip'

# Fix cascade.py - read with latin-1 (won't fail), then fix and write as utf-8
filepath = os.path.join(BASE, 'cascade.py')
with open(filepath, 'rb') as f:
    raw = f.read()

# Check if it's valid UTF-8
try:
    content = raw.decode('utf-8')
    print('cascade.py is valid UTF-8')
except UnicodeDecodeError as e:
    print(f'cascade.py has encoding error: {e}')
    # Try to fix by reading with errors='replace'
    content = raw.decode('utf-8', errors='replace')
    # Write back as proper UTF-8
    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print('Fixed cascade.py encoding')

# Also check other files
for fn in ['catalog.py', 'device_control.py', 'record.py', 'commander.py']:
    fp = os.path.join(BASE, fn)
    with open(fp, 'rb') as f:
        r = f.read()
    try:
        r.decode('utf-8')
        print(f'{fn} is valid UTF-8')
    except UnicodeDecodeError as e:
        print(f'{fn} has encoding error: {e}')
        c = r.decode('utf-8', errors='replace')
        with open(fp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(c)
        print(f'Fixed {fn} encoding')
