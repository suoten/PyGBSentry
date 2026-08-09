"""Find except Exception: pass violations in SIP core and API endpoint files."""
import os
import re

# SIP files checked by the test
sip_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "sip")
sip_files = ["talk.py", "handlers.py", "invite.py", "response_handler.py",
             "server.py", "dialog_manager.py", "catalog_runtime.py",
             "subscribe_manager.py", "watchdog.py"]

patterns = [
    r'except\s+Exception\s*:\s*\n\s*pass',
    r'except\s*:\s*\n\s*pass',
    r'except\s+Exception\s*:\s*pass',
]

print("=== SIP core files ===")
for fname in sip_files:
    fpath = os.path.join(sip_dir, fname)
    if not os.path.exists(fpath):
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    for pattern in patterns:
        matches = re.findall(pattern, content)
        if matches:
            print(f"  {fname}: {len(matches)} matches for pattern {pattern!r}")
            # Show line numbers
            for m in re.finditer(pattern, content):
                line_no = content[:m.start()].count('\n') + 1
                print(f"    line ~{line_no}: {m.group()!r}")

# API endpoint files (top-level only, no subdirs)
api_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "api", "v1", "endpoints")
print("\n=== API endpoint files (top-level only) ===")
for fname in os.listdir(api_dir):
    if not fname.endswith(".py"):
        continue
    fpath = os.path.join(api_dir, fname)
    if os.path.isdir(fpath):
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    # Only single-line pattern per test
    matches = re.findall(r'except\s+Exception\s*:\s*pass', content)
    if matches:
        print(f"  {fname}: {len(matches)} matches")
        for m in re.finditer(r'except\s+Exception\s*:\s*pass', content):
            line_no = content[:m.start()].count('\n') + 1
            print(f"    line ~{line_no}: {m.group()!r}")

print("\nDone.")
