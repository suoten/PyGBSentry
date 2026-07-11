"""
TDD tests for channel registration failure bug.

Bug: resources.default_stream_type column missing in SQLite database
causes all Resource queries to fail, preventing channels from being
registered and persisted after catalog sync.

Root cause: _ensure_missing_columns uses PRAGMA table_info within
the same transaction that created the table, which may return cached
results. The hardcoded SQLite fix in main.py didn't include
resources.default_stream_type.
"""

import pytest
import inspect
import textwrap


# ============================================================
# Bug: resources.default_stream_type column missing
# ============================================================

@pytest.mark.skip(reason="设计已变更为 JSON capabilities 字段，不再使用 default_stream_type 专用列")
class TestDefaultStreamTypeColumnFix:
    """Test that the missing column fix covers resources.default_stream_type."""

    def test_sqlite_fix_includes_default_stream_type(self):
        """
        GREEN: The hardcoded SQLite column fix in main.py should include
        resources.default_stream_type to prevent channel registration failure.
        """
        from app.main import app  # noqa: F401 - triggers module load
        import app.main as main_module

        source = inspect.getsource(main_module)

        # Verify the fix includes resources.default_stream_type
        assert "default_stream_type" in source, (
            "main.py should include default_stream_type in SQLite column fix"
        )
        assert '"resources"' in source or "'resources'" in source, (
            "main.py should include 'resources' table in SQLite column fix"
        )

    def test_default_stream_type_has_correct_type_and_default(self):
        """
        GREEN: The fix should use VARCHAR(16) DEFAULT 'main' for
        default_stream_type, matching the model definition.
        """
        import app.main as main_module

        source = inspect.getsource(main_module)

        # Verify correct type and default value
        assert "VARCHAR(16)" in source, (
            "default_stream_type should use VARCHAR(16) type"
        )
        assert "DEFAULT 'main'" in source, (
            "default_stream_type should default to 'main'"
        )

    def test_resource_model_has_default_stream_type(self):
        """
        GREEN: The Resource model should define default_stream_type column.
        """
        from app.models.resource import Resource

        # Verify the column exists in the model
        assert hasattr(Resource, 'default_stream_type'), (
            "Resource model should have default_stream_type column"
        )

        # Verify the default value
        col = Resource.__table__.c.default_stream_type
        assert col.default is not None, (
            "default_stream_type should have a default value"
        )

    def test_ensure_business_schema_includes_default_stream_type(self):
        """
        GREEN: ensure_business_schema (PostgreSQL path) should include
        the default_stream_type column migration.
        """
        from app.services.schema_upgrade import ensure_business_schema

        source = inspect.getsource(ensure_business_schema)

        assert "default_stream_type" in source, (
            "ensure_business_schema should include default_stream_type migration for PostgreSQL"
        )
        assert "VARCHAR(16)" in source, (
            "ensure_business_schema should use VARCHAR(16) for default_stream_type"
        )


@pytest.mark.skip(reason="schema_upgrade 已重构，不再使用 _ensure_missing_columns 函数")
class TestPragmaTableInfoCacheFix:
    """Test that PRAGMA table_info cache issue is fixed."""

    def test_ensure_missing_columns_uses_separate_connection_for_pragma(self):
        """
        GREEN: _ensure_missing_columns should use a separate connection
        for PRAGMA table_info to avoid cache issues in SQLite.
        """
        from app.services.schema_upgrade import _ensure_missing_columns

        source = inspect.getsource(_ensure_missing_columns)

        # Verify it uses a separate connection for PRAGMA
        assert "engine.connect()" in source, (
            "_ensure_missing_columns should use engine.connect() for PRAGMA table_info "
            "to avoid cache issues within the same transaction"
        )
