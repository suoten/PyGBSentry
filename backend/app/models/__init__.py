"""ORM model package.

This package intentionally has no explicit imports here — model modules are
discovered and imported on demand by :func:`app.db.model_registry.ensure_model_registry_loaded`
which walks this package's directory. Keeping ``__init__`` empty avoids import
cycles (many models are referenced lazily from services that must not be loaded
at model-import time).
"""
