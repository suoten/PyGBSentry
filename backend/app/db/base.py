"""SQLAlchemy declarative base for all ORM models.

All models under ``app/models/`` inherit from :class:`Base` defined here.
Using SQLAlchemy 2.0 ``DeclarativeBase`` (the recommended modern style),
which is fully compatible with the legacy ``Column``-based model definitions
used throughout the codebase (e.g. ``alarm.py``, ``record.py``).
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base.

    Subclassing ``DeclarativeBase`` is the SQLAlchemy 2.0 replacement for the
    legacy ``Base = declarative_base()`` call. Every ORM model must inherit
    from this class so that ``Base.metadata`` collects every mapped table —
    this is what ``model_registry`` and ``schema_upgrade`` rely on to create
    tables and run migrations.
    """

    pass
