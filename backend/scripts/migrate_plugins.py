import os
import re
import glob

PLUGINS = [
    "record_schedule_executor.py",
    "pull_proxy_monitor.py",
    "rtmp_push_channel_monitor.py",
    "snapshot_refresh.py",
    "webhook_pusher.py",
    "sip_logger.py",
    "network_watchdog.py",
    "stream_health.py",
    "stream_idle.py",
    "timelapse.py",
    "ptz_tour.py",
    "auto_record.py",
]

# Note: we skip record_index_verifier.py because it already exists in app/services/tasks/
# Wait, let's copy plugins/record_index_verifier.py to app/services/tasks/ as well just in case to override it or check if it's the same.
PLUGINS.append("record_index_verifier.py")

base_dir = r"e:\硕腾网络\gb28181\PyGBSentry\open-source\backend"
plugins_dir = os.path.join(base_dir, "plugins")
tasks_dir = os.path.join(base_dir, "app", "services", "tasks")

os.makedirs(tasks_dir, exist_ok=True)

for p in PLUGINS:
    src = os.path.join(plugins_dir, p)
    dst = os.path.join(tasks_dir, p)
    if not os.path.exists(src):
        print(f"Skipping {p}, not found in plugins/")
        continue
    
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Remove register function
    content = re.sub(r'def register\(.*?\):[\s\S]*?(?=\n\n|$)', '', content)
    # Remove HOOK_ON_STARTUP, HOOK_ON_SHUTDOWN imports
    content = re.sub(r'from app\.core\.plugin_manager import.*?\n', '', content)
    
    # Rename on_startup to start
    content = re.sub(r'async def _?on_startup\(\):', 'async def start():', content)
    # Rename on_shutdown to stop
    content = re.sub(r'async def _?on_shutdown\(\):', 'async def stop():', content)
    
    # Some files might not have a stop function, we can add a dummy one if it doesn't exist
    if 'async def stop():' not in content:
        content += '\n\nasync def stop():\n    pass\n'
    
    # Some files might not have start function if it was called _on_startup
    if 'async def start():' not in content:
        # try without async def just in case
        pass
        
    with open(dst, "w", encoding="utf-8") as f:
        f.write(content)
    
    os.remove(src)
    print(f"Moved {p} to {dst}")
    
# Remove from marketplace.json if needed
marketplace = os.path.join(plugins_dir, "marketplace.json")
if os.path.exists(marketplace):
    import json
    with open(marketplace, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    new_plugins = []
    for plugin in data.get("plugins", []):
        plugin_id = plugin.get("id")
        if plugin_id + ".py" not in PLUGINS:
            new_plugins.append(plugin)
            
    data["plugins"] = new_plugins
    with open(marketplace, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print("Updated marketplace.json")
