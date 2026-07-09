"""Media node cluster management endpoints.

Provides cluster status, node listing, and per-node health information
for dashboards and operational tooling.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.media_nodes_db import get_cluster_status

router = APIRouter()


@router.get("/cluster-status")
async def cluster_status(db: AsyncSession = Depends(get_db)):
    """Return the current media node cluster status.

    Returns total/online/offline node counts, per-node details, and
    aggregate stream count.
    """
    return await get_cluster_status(db)
