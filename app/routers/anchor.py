"""
Anchor routes: list anchors with sorting, filtering, and pagination.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, Literal

from app.database import get_db
from app.models import Anchor, Media, User, Follow
from app.security import current_user

router = APIRouter(prefix="/api", tags=["anchor"])


@router.get("/getAnchors")
def get_anchors( 
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    sort_by: Literal["like_count", "created_time", "follow_count", "fans_count"] = Query(
        default="like_count", description="Sort field"
    ),
    country: Optional[str] = Query(default=None, description="Filter by country"),
    language_code: Optional[str] = Query(default=None, description="Filter by language code"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page")
):
    """
    List anchors with sorting, filtering, and pagination.
    
    - sort_by: Sort by like_count (default), created_time, follow_count, or fans_count (all descending)
    - country: Filter anchors by country
    - language_code: Filter anchors by language code
    - page: Page number (default 1)
    - page_size: Items per page (default 20, max 100)
    """
    # Build base query
    query = db.query(Anchor)
    
    # Apply filters
    if country:
        query = query.filter(Anchor.country == country)
    
    if language_code:
        query = query.filter(Anchor.language_code == language_code)
    
    # Apply sorting (always descending)
    sort_column = getattr(Anchor, sort_by)
    query = query.order_by(desc(sort_column))
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * page_size
    anchors = query.offset(offset).limit(page_size).all()
    
    # Build response with media for each anchor
    items = []
    for anchor in anchors:
        anchor_dict = anchor.to_dict()
        # Query media for this anchor
        medias = db.query(Media).filter(Media.user_id == str(anchor.user_id)).all()
        anchor_dict["media_list"] = [media.to_dict() for media in medias]
        anchor_dict["is_hot"] = anchor.fans_count > 10000  # Example logic for "hot" anchors
        anchor_dict["is_new"] = (anchor.created_time is not None and (datetime.now(timezone.utc) - anchor.created_time).days <= 30)  # Example logic for "new" anchors
        anchor_dict["online_status"] = 1 if anchor.is_check else 0
        
        # Check if user is following this anchor
        is_following = db.query(Follow).filter(
            Follow.user_id == str(user.user_id),
            Follow.follow_user_id == str(anchor.user_id),
        ).first() is not None
        anchor_dict["is_following"] = is_following
        
        items.append(anchor_dict)
    
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }   
