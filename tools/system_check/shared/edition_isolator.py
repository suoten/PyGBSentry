from __future__ import annotations

from tools.system_check.shared.models import RouteInfo


class EditionIsolator:
    OSS_ONLY_PREFIXES: set[str] = {
        "/setup", "/ops", "/logs", "/alarms", "/blacklist", "/work-orders",
        "/health", "/talk", "/map", "/command", "/structured", "/hook",
        "/stream", "/stream-opt", "/media", "/devices", "/integrations",
        "/push-channels", "/proxy", "/trace-events", "/system-config",
        "/config-center", "/release-center", "/audit-center", "/control",
        "/record", "/vod", "/gb-record", "/record-schedule", "/regions",
        "/organizations", "/device-record", "/platforms", "/rtp",
        "/asset-management", "/network", "/reports", "/ai", "/demo",
        "/metrics", "/apps", "/ptz", "/ssl-cert",
    }

    SERVER_ONLY_PREFIXES: set[str] = {
        "/developer", "/portal", "/portal-public", "/legal",
        "/public", "/admin",
    }

    @classmethod
    def classify_route(cls, route: RouteInfo) -> str:
        if route.edition_scope != "both":
            return route.edition_scope
        path = route.full_path or route.path
        for prefix in cls.OSS_ONLY_PREFIXES:
            if path.startswith(prefix) or path.startswith(f"/api/v1{prefix}"):
                return "oss"
        for prefix in cls.SERVER_ONLY_PREFIXES:
            if path.startswith(prefix) or path.startswith(f"/api/v1{prefix}"):
                return "server"
        return "both"

    @classmethod
    def filter_routes_for_edition(
        cls, routes: list[RouteInfo], target_edition: str
    ) -> list[RouteInfo]:
        filtered: list[RouteInfo] = []
        for route in routes:
            scope = cls.classify_route(route)
            if scope == "both" or scope == target_edition:
                route.edition_scope = scope
                filtered.append(route)
        return filtered

    @classmethod
    def should_skip_reverse_check(
        cls, route: RouteInfo, target_edition: str
    ) -> bool:
        scope = cls.classify_route(route)
        if scope == "both":
            return False
        if target_edition == "open-source" and scope == "server":
            return True
        if target_edition == "server" and scope == "oss":
            return True
        return False
