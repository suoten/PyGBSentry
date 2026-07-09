#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check which endpoint modules fail to import and why."""
import importlib
import sys
import os

os.chdir(r"e:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend")
sys.path.insert(0, ".")

modules = [
    "devices", "users", "platforms", "system_config", "stream",
    "proxy_compat", "talk", "map", "config_center", "reports",
    "audit_center", "roles", "media", "vod", "control", "command",
    "structured", "rtp", "setup", "demo", "apps", "integrations",
    "push_channels", "trace_events", "release_center", "channel_import",
    "asset_management", "network", "network_diagnostics",
    "stream_optimization", "ssl_cert", "ai_gateway", "work_orders",
    "billing", "plugins", "gb_record", "regions", "organizations",
    "user_api_keys",
]

for m in modules:
    try:
        mod = importlib.import_module(f"app.api.v1.endpoints.{m}")
        router = getattr(mod, "router", None)
        print(f"  OK   {m} (router={router is not None})")
    except Exception as e:
        print(f"  FAIL {m}: {str(e)[:150]}")
