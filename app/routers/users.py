"""
User information routes.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import GoogleAttribution
from app.security import current_user, current_user_readonly

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/user/info")
async def get_user_info(user: User = Depends(current_user_readonly)):
    """Get current user information."""
    return {"code": 200, "data": user.to_dict()}


@router.post("/user/googleAttribution")
async def set_user_attribution(
    attribution: GoogleAttribution,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set user attribution."""
    user.install_referrer = attribution.install_referrer
    user.referrer_click_timestamp_seconds = attribution.referrer_click_timestamp_seconds
    user.install_begin_timestamp_seconds = attribution.install_begin_timestamp_seconds
    user.referrer_click_timestamp_server_seconds = attribution.referrer_click_timestamp_server_seconds
    user.install_begin_timestamp_server_seconds = attribution.install_begin_timestamp_server_seconds
    user.install_version = attribution.install_version
    user.google_play_instant = attribution.google_play_instant
    return {"code": 200, "msg": "success"}
