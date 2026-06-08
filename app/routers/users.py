"""
User information routes.
"""
from fastapi import APIRouter, Depends

from app.models import User
from app.security import current_user

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/user/info")
def get_user_info(user: User = Depends(current_user)):
    """Get current user information."""
    return {
        "code": 200,
        "data": {"user_id": user.id, "device_id": user.device_id}
    }
