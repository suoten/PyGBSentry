from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.v1.endpoints.stream import play_stream
from app.db.session import get_db
from app.models.user import User

router = APIRouter()


@router.api_route("/start/{device_id}/{channel_id}", methods=["GET", "POST"])
async def start_play(
    device_id: str,
    channel_id: str,
    stream_type: str = Query("auto", alias="streamType"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await play_stream(
        device_id=device_id,
        channel_id=channel_id,
        stream_type=stream_type or "auto",
        db=db,
        current_user=current_user,
    )
