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


@router.get("/users")
def list_users(page: int = 1, page_size: int = 20, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Return paginated list of users.

    - `page`: 1-based page number
    - `page_size`: items per page (max 100)
    """
    if page < 1 or page_size < 1:
        raise HTTPException(status_code=400, detail="page and page_size must be >= 1")

    page_size = min(page_size, 100)
    total = db.query(func.count(User.id)).scalar() or 0
    offset = (page - 1) * page_size
    rows: List[User] = db.query(User).order_by(User.id).offset(offset).limit(page_size).all()
    items = [r.to_dict() for r in rows]

    return {
        "code": 200,
        "data": {"total": total, "page": page, "page_size": page_size, "items": items}
    }
