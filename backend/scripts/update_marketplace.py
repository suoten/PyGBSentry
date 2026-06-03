import os
import json

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
    "record_index_verifier.py"
]

base_dir = r"e:\硕腾网络\gb28181\PyGBSentry\open-source\backend"
plugins_dir = os.path.join(base_dir, "plugins")
marketplace = os.path.join(plugins_dir, "marketplace.json")

if os.path.exists(marketplace):
    with open(marketplace, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if isinstance(data, list):
        new_plugins = []
        for plugin in data:
            plugin_id = plugin.get("id")
            if plugin_id + ".py" not in PLUGINS:
                new_plugins.append(plugin)
        
        with open(marketplace, "w", encoding="utf-8") as f:
            json.dump(new_plugins, f, indent=4, ensure_ascii=False)
        print("Updated marketplace.json")
