from __future__ import annotations

from pathlib import Path

from tools.system_check.parsers.backend_route_parser import BackendRouteParser
from tools.system_check.parsers.frontend_api_parser import FrontendApiParser
from tools.system_check.shared.edition_isolator import EditionIsolator
from tools.system_check.shared.models import (
    ApiConsistencyResult,
    ApiCallInfo,
    MatchStatus,
    MismatchResult,
    RouteInfo,
    Severity,
)
from tools.system_check.shared.path_matcher import PathMatcher


class ApiConsistencyAnalyzer:
    INTERNAL_API_PREFIXES = {"/ping", "/docs", "/openapi.json", "/redoc"}

    @classmethod
    def analyze(
        cls,
        edition: str,
        backend_api_file: str | Path,
        frontend_src_dir: str | Path,
        frontend_api_dir: str | Path | None = None,
        frontend_views_dir: str | Path | None = None,
        frontend_composable_dir: str | Path | None = None,
    ) -> ApiConsistencyResult:
        backend_routes = BackendRouteParser.parse_all_routes(backend_api_file)
        backend_routes = EditionIsolator.filter_routes_for_edition(backend_routes, edition)

        frontend_calls: list[ApiCallInfo] = []
        if frontend_api_dir and Path(frontend_api_dir).exists():
            frontend_calls.extend(FrontendApiParser.parse_api_directory(frontend_api_dir))
        if frontend_views_dir and Path(frontend_views_dir).exists():
            frontend_calls.extend(FrontendApiParser.parse_views_api_calls(frontend_views_dir))
        if frontend_composable_dir and Path(frontend_composable_dir).exists():
            frontend_calls.extend(FrontendApiParser.parse_composable_api_calls(frontend_composable_dir))

        frontend_calls = cls._deduplicate_calls(frontend_calls)

        forward_mismatches = cls.check_forward_coverage(frontend_calls, backend_routes)
        reverse_mismatches = cls.check_reverse_coverage(backend_routes, frontend_calls, edition)

        matched_count = len(frontend_calls) - len(forward_mismatches)

        return ApiConsistencyResult(
            edition=edition,
            forward_mismatches=forward_mismatches,
            reverse_mismatches=reverse_mismatches,
            total_frontend_calls=len(frontend_calls),
            total_backend_routes=len(backend_routes),
            matched_count=max(0, matched_count),
        )

    @classmethod
    def check_forward_coverage(
        cls, frontend_calls: list[ApiCallInfo], backend_routes: list[RouteInfo]
    ) -> list[MismatchResult]:
        mismatches: list[MismatchResult] = []
        backend_paths = [PathMatcher.normalize_path(r.full_path or r.path) for r in backend_routes]
        backend_method_path = {(r.method, PathMatcher.normalize_path(r.full_path or r.path)) for r in backend_routes}

        for call in frontend_calls:
            norm_call_path = PathMatcher.normalize_path(call.path)
            exact_match = (call.method, norm_call_path) in backend_method_path

            if exact_match:
                continue

            fuzzy_results = PathMatcher.match(norm_call_path, backend_paths)
            if fuzzy_results and fuzzy_results[0][1] >= 0.8:
                matched_path = fuzzy_results[0][0]
                matched_route = next(
                    (r for r in backend_routes
                     if PathMatcher.normalize_path(r.full_path or r.path) == matched_path and r.method == call.method),
                    None,
                )
                if matched_route:
                    continue

            has_partial = any(
                r.method == call.method and PathMatcher.is_match(norm_call_path, PathMatcher.normalize_path(r.full_path or r.path), 0.5)
                for r in backend_routes
            )

            if has_partial:
                mismatches.append(MismatchResult(
                    match_status=MatchStatus.DYNAMIC_NEEDS_REVIEW,
                    severity=Severity.MEDIUM,
                    direction="frontend→backend",
                    method=call.method,
                    path=call.path,
                    frontend_call=call,
                    detail="⚠️ 动态路径，需人工确认",
                ))
            else:
                mismatches.append(MismatchResult(
                    match_status=MatchStatus.MISSING_BACKEND,
                    severity=Severity.HIGH,
                    direction="frontend→backend",
                    method=call.method,
                    path=call.path,
                    frontend_call=call,
                    detail=f"前端调用 {call.method} {call.path} 在后端无对应路由",
                ))

        return mismatches

    @classmethod
    def check_reverse_coverage(
        cls, backend_routes: list[RouteInfo], frontend_calls: list[ApiCallInfo], edition: str = ""
    ) -> list[MismatchResult]:
        mismatches: list[MismatchResult] = []
        frontend_method_path = {
            (c.method, PathMatcher.normalize_path(c.path)) for c in frontend_calls
        }

        for route in backend_routes:
            if EditionIsolator.should_skip_reverse_check(route, edition):
                continue

            if cls._is_internal_api(route):
                continue

            norm_route_path = PathMatcher.normalize_path(route.full_path or route.path)
            exact_match = (route.method, norm_route_path) in frontend_method_path

            if exact_match:
                continue

            frontend_paths = [PathMatcher.normalize_path(c.path) for c in frontend_calls if c.method == route.method]
            fuzzy_results = PathMatcher.match(norm_route_path, frontend_paths)

            if fuzzy_results and fuzzy_results[0][1] >= 0.8:
                continue

            if route.is_deprecated:
                mismatches.append(MismatchResult(
                    match_status=MatchStatus.DEPRECATED,
                    severity=Severity.MEDIUM,
                    direction="backend→frontend",
                    method=route.method,
                    path=route.full_path or route.path,
                    backend_route=route,
                    detail="⚠️ 废弃端点，前端未调用（正常）",
                ))
            else:
                mismatches.append(MismatchResult(
                    match_status=MatchStatus.MISSING_FRONTEND,
                    severity=Severity.LOW,
                    direction="backend→frontend",
                    method=route.method,
                    path=route.full_path or route.path,
                    backend_route=route,
                    detail=f"后端路由 {route.method} {route.full_path or route.path} 在前端无调用",
                ))

        return mismatches

    @classmethod
    def _is_internal_api(cls, route: RouteInfo) -> bool:
        path = route.full_path or route.path
        return any(path.startswith(prefix) or PathMatcher.normalize_path(path).startswith(prefix) for prefix in cls.INTERNAL_API_PREFIXES)

    @classmethod
    def _deduplicate_calls(cls, calls: list[ApiCallInfo]) -> list[ApiCallInfo]:
        seen: set[tuple[str, str, str]] = set()
        unique: list[ApiCallInfo] = []
        for call in calls:
            key = (call.method, call.path, call.file_path)
            if key not in seen:
                seen.add(key)
                unique.append(call)
        return unique
