"""
User information routes.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User
from app.security import current_user
from app.database import get_db

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/user/info")
def get_user_info(user: User = Depends(current_user)):
    """Get current user information."""
    return {
        "code": 200,
        "data": user.to_dict()
    }
