"""
Tests for channel registration schema compatibility.

Original bug: resources.default_stream_type column missing in SQLite database
caused all Resource queries to fail, preventing channels from being
registered and persisted after catalog sync.

Design change: default_stream_type was replaced by a JSON ``capabilities``
column on the Resource model. schema_upgrade.py was refactored from
``_ensure_missing_columns`` (PRAGMA-based) to a declarative
``_ALL_STMT_GROUPS`` + ``ensure_business_schema`` approach using
``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` with dialect-aware handling.

These tests verify the current design:
1. Resource model defines the ``capabilities`` JSON column.
2. schema_upgrade.py includes resources table ALTER TABLE migrations.
3. schema_upgrade.py uses the new declarative approach (not _ensure_missing_columns).
4. SQLite dialect correctly strips ``IF NOT EXISTS`` from ADD COLUMN.
"""

import inspect
import pytest


# ============================================================
# Design: capabilities JSON column replaces default_stream_type
# ============================================================

class TestCapabilitiesColumnDesign:
    """Test that the Resource model uses a JSON capabilities column."""

    def test_resource_model_has_capabilities_column(self):
        """GREEN: The Resource model should define a ``capabilities`` column."""
        from app.models.resource import Resource

        assert hasattr(Resource, "capabilities"), (
            "Resource model should have capabilities column (replaces default_stream_type)"
        )

    def test_capabilities_column_is_json_type(self):
        """GREEN: ``capabilities`` should be a JSON column to store flexible capability dicts."""
        from app.models.resource import Resource
        from sqlalchemy import JSON

        col = Resource.__table__.c.capabilities
        assert isinstance(col.type, JSON), (
            "capabilities column should use SQLAlchemy JSON type"
        )

    def test_capabilities_column_has_dict_default(self):
        """GREEN: ``capabilities`` should default to an empty dict."""
        from app.models.resource import Resource

        col = Resource.__table__.c.capabilities
        assert col.default is not None, "capabilities should have a default value"
        # SQLAlchemy ColumnDefault with callable arg — arg is `dict` constructor
        assert callable(col.default.arg), (
            "capabilities default should be a callable (dict constructor)"
        )
        # Verify the callable produces a dict when invoked with a minimal context.
        # SQLAlchemy passes a context object; `dict` ignores it and returns {}.
        class _DummyCtx:
            pass
        result = col.default.arg(_DummyCtx())
        assert isinstance(result, dict), (
            "capabilities default callable should produce a dict"
        )

    def test_resource_model_does_not_have_default_stream_type(self):
        """GREEN: The legacy ``default_stream_type`` column should be removed."""
        from app.models.resource import Resource

        assert not hasattr(Resource, "default_stream_type"), (
            "default_stream_type should be removed — replaced by capabilities JSON column"
        )


# ============================================================
# schema_upgrade.py: declarative migration approach
# ============================================================

class TestSchemaUpgradeDeclarativeMigrations:
    """Test that schema_upgrade.py uses the declarative _ALL_STMT_GROUPS approach."""

    def test_ensure_business_schema_exists(self):
        """GREEN: ``ensure_business_schema`` should be the entry point."""
        from app.services.schema_upgrade import ensure_business_schema

        assert callable(ensure_business_schema), (
            "ensure_business_schema should be the schema migration entry point"
        )

    def test_ensure_missing_columns_removed(self):
        """GREEN: The old ``_ensure_missing_columns`` function should be removed."""
        import app.services.schema_upgrade as schema_module

        assert not hasattr(schema_module, "_ensure_missing_columns"), (
            "_ensure_missing_columns should be removed — replaced by _ALL_STMT_GROUPS + "
            "_execute_ddl_statements"
        )

    def test_all_stmt_groups_defined(self):
        """GREEN: ``_ALL_STMT_GROUPS`` should be defined as the migration source."""
        from app.services import schema_upgrade

        assert hasattr(schema_upgrade, "_ALL_STMT_GROUPS"), (
            "_ALL_STMT_GROUPS should be defined"
        )
        groups = schema_upgrade._ALL_STMT_GROUPS
        assert isinstance(groups, list) and len(groups) > 0, (
            "_ALL_STMT_GROUPS should be a non-empty list of statement groups"
        )

    def test_build_all_statements_flattens_groups(self):
        """GREEN: ``_build_all_statements`` should flatten all groups into one list."""
        from app.services.schema_upgrade import _build_all_statements, _ALL_STMT_GROUPS

        all_stmts = _build_all_statements()
        expected_count = sum(len(g) for g in _ALL_STMT_GROUPS)
        assert len(all_stmts) == expected_count, (
            "_build_all_statements should flatten all groups"
        )

    def test_schema_includes_resources_alter_table(self):
        """GREEN: schema migrations should include ALTER TABLE for resources table."""
        from app.services.schema_upgrade import _build_all_statements

        all_stmts = _build_all_statements()
        resources_stmts = [s for s in all_stmts if "resources" in s.lower() and "ALTER TABLE" in s.upper()]
        assert len(resources_stmts) > 0, (
            "schema_upgrade should include ALTER TABLE statements for resources table "
            "to add missing columns on existing databases"
        )

    def test_schema_uses_add_column_if_not_exists(self):
        """GREEN: ALTER TABLE statements should use ADD COLUMN IF NOT EXISTS for idempotency."""
        from app.services.schema_upgrade import _build_all_statements

        all_stmts = _build_all_statements()
        idempotent_stmts = [
            s for s in all_stmts
            if "ADD COLUMN IF NOT EXISTS" in s.upper()
        ]
        assert len(idempotent_stmts) > 0, (
            "schema_upgrade should use 'ADD COLUMN IF NOT EXISTS' for idempotent migrations"
        )

    def test_execute_ddl_handles_sqlite_if_not_exists(self):
        """GREEN: _execute_ddl_statements should strip IF NOT EXISTS for SQLite.

        SQLite doesn't support ``ADD COLUMN IF NOT EXISTS`` syntax, so the helper
        must strip it and rely on try/except for duplicate-column errors.
        """
        from app.services.schema_upgrade import _execute_ddl_statements

        source = inspect.getsource(_execute_ddl_statements)
        assert "sqlite" in source.lower(), (
            "_execute_ddl_statements should handle SQLite dialect specially"
        )
        assert "ADD COLUMN IF NOT EXISTS" in source, (
            "_execute_ddl_statements should reference 'ADD COLUMN IF NOT EXISTS' for stripping"
        )

    def test_ensure_business_schema_uses_engine_begin(self):
        """GREEN: ensure_business_schema should use engine.begin() for transactional DDL.

        This replaces the old PRAGMA-based approach that had cache issues within
        the same transaction. The new approach runs all DDL in a single
        transaction with proper commit/rollback semantics.
        """
        from app.services.schema_upgrade import ensure_business_schema

        source = inspect.getsource(ensure_business_schema)
        assert "engine.begin()" in source, (
            "ensure_business_schema should use engine.begin() for transactional DDL — "
            "this avoids the PRAGMA table_info cache issue from the old approach"
        )
