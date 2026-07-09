"""Security guard test: ZLM API secret must NOT be passed via URL query params.

P-SEC: ZLMediaKit API secret was previously passed as a URL query parameter
(``params={"secret": ...}`` in GET requests), causing it to appear in proxy
logs, access logs, and browser history. This test statically verifies that
no source file under ``app/`` passes the ZLM secret via URL query params.

ZLMediaKit does NOT support HTTP header-based authentication — its RESTful API
only accepts ``secret`` as a URL query parameter or POST form body. We use
POST with ``data=`` (form body) for all ZLM API calls, which keeps the secret
out of URLs and access logs.
"""
import os
import re
import unittest
from pathlib import Path


_APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Pattern: params={"secret": ...} as a keyword argument (not a variable name).
# The negative lookbehind (?<![a-zA-Z_]) ensures "params" is not part of a
# longer identifier like "close_stream_params" or "check_params".
_PARAMS_SECRET_PATTERN = re.compile(
    r"(?<![a-zA-Z_])params\s*=\s*\{[^}]*['\"]secret['\"]\s*:",
    re.IGNORECASE,
)

# Pattern: client.get(... index/api ...) — GET requests to ZLM API endpoints
# All ZLM API calls should use POST, not GET.
_GET_ZLM_API_PATTERN = re.compile(
    r"\.get\([^)]*index/api",
    re.IGNORECASE,
)

# Pattern: secret interpolated into URL string (e.g., f"...?secret={...}")
_SECRET_IN_URL_PATTERN = re.compile(
    r"['\"].*secret=\{.*\}.*['\"]",
    re.IGNORECASE,
)


class TestNoZlmSecretInUrl(unittest.TestCase):
    """Verify no ZLM API secret is passed via URL query params."""

    def _scan_python_files(self) -> list[Path]:
        """Collect all .py files under app/, excluding __pycache__."""
        files = []
        for p in _APP_DIR.rglob("*.py"):
            if "__pycache__" in str(p):
                continue
            files.append(p)
        return files

    def test_no_params_with_secret_in_url_query(self):
        """No file should contain params={"secret": ...} (secret in URL query)."""
        violations = []
        for py_file in self._scan_python_files():
            try:
                content = py_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if _PARAMS_SECRET_PATTERN.search(line):
                    violations.append(f"{py_file.name}:{lineno}: {line.strip()}")

        self.assertEqual(
            violations, [],
            f"Found {len(violations)} location(s) passing ZLM secret via URL "
            f"query params (params={{'secret': ...}}). Use POST with data= instead:\n"
            + "\n".join(violations),
        )

    def test_no_get_requests_to_zlm_api(self):
        """No file should use client.get() to call ZLM /index/api/ endpoints.

        ZLMediaKit API calls must use POST to keep secret in request body.
        """
        violations = []
        for py_file in self._scan_python_files():
            try:
                content = py_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                # Skip comment lines
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if _GET_ZLM_API_PATTERN.search(line):
                    violations.append(f"{py_file.name}:{lineno}: {line.strip()}")

        self.assertEqual(
            violations, [],
            f"Found {len(violations)} GET request(s) to ZLM /index/api/ endpoints. "
            f"All ZLM API calls must use POST to keep secret out of URLs:\n"
            + "\n".join(violations),
        )

    def test_no_secret_interpolated_in_url_string(self):
        """No file should interpolate secret into a URL string literal."""
        violations = []
        for py_file in self._scan_python_files():
            try:
                content = py_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if _SECRET_IN_URL_PATTERN.search(line):
                    violations.append(f"{py_file.name}:{lineno}: {line.strip()}")

        self.assertEqual(
            violations, [],
            f"Found {len(violations)} location(s) with secret interpolated into "
            f"URL string. Use POST body instead:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
