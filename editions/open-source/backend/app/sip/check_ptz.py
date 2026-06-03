import sys
import os

_ptz_path = os.path.join(os.path.dirname(__file__), "ptz.py")
try:
    with open(_ptz_path, "rb") as f:
        data = f.read()
except FileNotFoundError:
    print(f"ERROR: ptz.py not found at {_ptz_path}")
    sys.exit(1)
# FIXED: bare open() without with/try-catch/close and hardcoded absolute path
idx = data.find(b'Send PTZ')
h = data[idx-20:idx+120].hex()
print(' '.join([h[i:i+2] for i in range(0, len(h), 2)]))
# Also check for BOM
print(f"BOM: {data[:3]}")
print(f"File size: {len(data)}")
# Check around line 91-93
lines = data.split(b'\n')
for i in range(88, min(96, len(lines))):
    print(f"Line {i+1}: {repr(lines[i][:100])}")
