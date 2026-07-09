"""Model registry — ensures all ORM models are imported and registered on Base.metadata.

SQLAlchemy only registers a model's table in ``Base.metadata`` when the model
class is actually imported. ``schema_upgrade`` and ``Base.metadata.create_all``
therefore need every model module under ``app/models/`` to be imported first.

``ensure_model_registry_loaded()`` walks the models package and imports every
module exactly once, idempotently. It is safe to call repeatedly.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Set

from loguru import logger

from app.db.base import Base

_LOADED: Set[str] = set()
_LOAD_LOCK_INITIATED = False


def _iter_model_module_names() -> list[str]:
    """Return the dotted import names of all modules under ``app.models``.

    Mirrors the directory layout at import time so new model files are picked
    up automatically without editing this registry.
    """
    import app.models as models_pkg

    names: list[str] = []
    package_path = getattr(models_pkg, "__path__", None)
    if not package_path:
        return names
    for mod_info in pkgutil.iter_modules(package_path):
        if mod_info.ispkg:
            continue
        names.append(f"app.models.{mod_info.name}")
    return sorted(names)


def ensure_model_registry_loaded() -> None:
    """Import every model module so all tables are registered on ``Base.metadata``.

    Idempotent and safe to call from multiple call sites (startup, migrations,
    tests). Import errors in a single model module are logged but do not abort
    registration of the remaining modules — a missing optional model should not
    prevent the core schema from being created.
    """
    global _LOAD_LOCK_INITIATED
    if _LOAD_LOCK_INITIATED:
        # Already fully loaded; cheap fast-path for repeated callers.
        if len(_LOADED) >= len(_iter_model_module_names()):
            return

    module_names = _iter_model_module_names()
    for name in module_names:
        if name in _LOADED:
            continue
        try:
            importlib.import_module(name)
            _LOADED.add(name)
        except Exception as e:
            logger.warning(
                "model_registry: failed to import '{}' ({}); "
                "its table may be missing from Base.metadata",
                name,
                e,
            )
            # Mark as attempted so we don't retry on every call site.
            _LOADED.add(name)

    _LOAD_LOCK_INITIATED = True
    registered_tables = sorted(Base.metadata.tables.keys())
    logger.debug(
        "model_registry: loaded {} module(s), {} table(s) registered on Base.metadata",
        len(_LOADED),
        len(registered_tables),
    )


def get_registered_table_names() -> list[str]:
    """Return the table names currently registered on ``Base.metadata``.

    Calls :func:`ensure_model_registry_loaded` first to guarantee the registry
    is populated.
    """
    ensure_model_registry_loaded()
    return sorted(Base.metadata.tables.keys())
