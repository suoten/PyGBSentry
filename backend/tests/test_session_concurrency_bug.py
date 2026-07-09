"""
TDD tests for SQLAlchemy async session concurrency bugs.

Bug2: _resolve_media_mode uses asyncio.gather with the same session,
      causing "Method 'close()' can't be called here" error.

Bug3: _send_invite_common_inner uses asyncio.create_task to concurrently
      execute _select_media_node(_db) and _resolve_media_mode, causing
      connection pool leaks and session state corruption.
"""

import ast
import inspect
import textwrap
import pytest


class TestResolveMediaModeNoConcurrentSession:
    """Bug2: _resolve_media_mode should not use asyncio.gather on the same session."""

    def test_resolve_media_mode_no_gather(self):
        """
        GREEN: _resolve_media_mode should NOT use asyncio.gather
        to execute two queries on the same session concurrently.
        """
        from app.sip.invite import SipInvite
        import ast
        import textwrap

        source = inspect.getsource(SipInvite._resolve_media_mode)
        source = textwrap.dedent(source)

        # Parse AST and check for asyncio.gather calls in actual code (not comments)
        tree = ast.parse(source)
        has_gather = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == 'gather':
                    if isinstance(func.value, ast.Name) and func.value.id == 'asyncio':
                        has_gather = True

        assert not has_gather, (
            "_resolve_media_mode should not use asyncio.gather - "
            "SQLAlchemy async session does not support concurrent operations"
        )

    def test_resolve_media_mode_uses_sequential_queries(self):
        """
        GREEN: _resolve_media_mode should execute queries sequentially.
        """
        from app.sip.invite import SipInvite

        source = inspect.getsource(SipInvite._resolve_media_mode)

        # Should contain two sequential execute calls
        assert source.count("await session.execute") == 2, (
            "_resolve_media_mode should have two sequential session.execute calls"
        )


class TestSendInviteNoConcurrentSession:
    """Bug3: _send_invite_common_inner should not use asyncio.create_task
    to concurrently execute tasks that share the same session."""

    def test_send_invite_no_create_task_with_db_session(self):
        """
        GREEN: _send_invite_common_inner should NOT pass _db session
        to asyncio.create_task, which would cause concurrent session access.
        """
        from app.sip.invite import SipInvite

        source = inspect.getsource(SipInvite._send_invite_common_inner)

        # Should NOT contain create_task with _db
        assert "create_task" not in source or "_db" not in source.split("create_task")[0][-50:], (
            "_send_invite_common_inner should not use asyncio.create_task with _db session - "
            "this causes concurrent session access and connection pool leaks"
        )

    def test_send_invite_sequential_execution(self):
        """
        GREEN: _send_invite_common_inner should execute DB-dependent
        operations sequentially, not concurrently.
        """
        from app.sip.invite import SipInvite

        source = inspect.getsource(SipInvite._send_invite_common_inner)

        # Should use await (sequential) instead of create_task (concurrent)
        # for _select_media_node and _resolve_media_mode
        assert "await self._select_media_node" in source, (
            "_send_invite_common_inner should use 'await self._select_media_node' sequentially"
        )
        assert "await self._resolve_media_mode" in source or "media_mode_override" in source, (
            "_send_invite_common_inner should resolve media mode sequentially"
        )
