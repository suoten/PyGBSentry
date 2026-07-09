"""API version negotiation and deprecation framework.

Provides middleware-level support for:
1. **Version negotiation** — clients can specify the desired API version via:
   - URL path prefix (``/api/v1/...``, ``/api/v2/...``) — primary mechanism
   - ``Accept-Version`` header — optional override
   - ``Accept: application/json; version=1`` content-type parameter — fallback

2. **Deprecation warnings** — deprecated versions receive a ``Deprecation`` and
   ``Sunset`` header in the response, plus a ``Link`` rel="deprecation" header
   pointing to the migration guide.

Current version policy:
- ``v1`` — **stable** (active)
- ``v2`` — not yet released (placeholder for future)

Usage in ``main.py``::

    from app.api.versioning import APIVersionMiddleware
    app.add_middleware(APIVersionMiddleware)
"""
from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Version registry
# ---------------------------------------------------------------------------

#: Active API versions in priority order. ``v1`` is current; ``v2`` reserved.
ACTIVE_VERSIONS: tuple[str, ...] = ("v1",)

#: Default version when the client does not specify one.
DEFAULT_VERSION = "v1"

#: Deprecated versions with their sunset date and migration URL.
#: Empty dict means no deprecated versions yet.
DEPRECATED_VERSIONS: dict[str, dict[str, str]] = {
    # "v0": {"sunset": "Sat, 01 Jan 2025 00:00:00 GMT", "migration_url": "/docs/migration-v0-to-v1"},
}

#: Version negotiation header names.
ACCEPT_VERSION_HEADER = "Accept-Version"
DEPRECATION_HEADER = "Deprecation"
SUNSET_HEADER = "Sunset"
LINK_HEADER = "Link"

#: URL prefix that identifies API version in the path.
API_PATH_PREFIX = "/api/"


def negotiate_version(request: Request) -> str:
    """Determine the API version the client wants.

    Priority:
    1. URL path prefix (``/api/v1/...``)
    2. ``Accept-Version`` header
    3. ``Accept`` content-type parameter ``version=N``
    4. :data:`DEFAULT_VERSION`
    """
    # 1. URL path
    path = request.url.path
    if path.startswith(API_PATH_PREFIX):
        remainder = path[len(API_PATH_PREFIX):]
        for v in ACTIVE_VERSIONS:
            if remainder.startswith(v + "/") or remainder == v:
                return v

    # 2. Accept-Version header
    accept_version = request.headers.get(ACCEPT_VERSION_HEADER, "").strip().lower()
    if accept_version:
        # Normalise "1" → "v1"
        if not accept_version.startswith("v"):
            accept_version = f"v{accept_version}"
        if accept_version in ACTIVE_VERSIONS:
            return accept_version

    # 3. Accept header with version parameter
    accept = request.headers.get("accept", "")
    if "version=" in accept:
        for part in accept.split(";"):
            part = part.strip()
            if part.startswith("version="):
                ver = part.split("=", 1)[1].strip().strip('"').lower()
                if not ver.startswith("v"):
                    ver = f"v{ver}"
                if ver in ACTIVE_VERSIONS:
                    return ver

    # 4. Default
    return DEFAULT_VERSION


def is_deprecated(version: str) -> bool:
    """Check if a version is deprecated."""
    return version in DEPRECATED_VERSIONS


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Middleware that adds version negotiation and deprecation headers.

    For every ``/api/`` request:
    - Negotiates the API version
    - If the version is deprecated, adds ``Deprecation``, ``Sunset``, and
      ``Link`` headers to the response
    - Adds ``X-API-Version`` header to the response for transparency
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Dispatch."""
        # Only process API requests
        if not request.url.path.startswith(API_PATH_PREFIX):
            return await call_next(request)

        version = negotiate_version(request)

        response = await call_next(request)

        # Add the negotiated version to the response for client transparency
        response.headers["X-API-Version"] = version

        # Add deprecation headers if applicable
        if is_deprecated(version):
            deprecation_info = DEPRECATED_VERSIONS[version]
            response.headers[DEPRECATION_HEADER] = "true"
            if "sunset" in deprecation_info:
                response.headers[SUNSET_HEADER] = deprecation_info["sunset"]
            if "migration_url" in deprecation_info:
                response.headers[LINK_HEADER] = f'<{deprecation_info["migration_url"]}>; rel="deprecation"; type="text/html"'

        return response
