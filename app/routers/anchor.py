"""
Anchor routes: list anchors with sorting, filtering, and pagination.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_readonly
from app.models import Anchor, Media, User, UserFollow, UserLike
from app.security import current_user_readonly

router = APIRouter(prefix="/api", tags=["anchor"])


@router.get("/getAnchors")
async def get_anchors(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    sort_by: Literal["like_count", "created_time", "follow_count", "fans_count"] = Query(
        default="like_count", description="Sort field"
    ),
    country: Optional[str] = Query(default=None, description="Filter by country"),
    language_code: Optional[str] = Query(default=None, description="Filter by language code"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
):
    query = select(Anchor)

    if country:
        query = query.where(Anchor.country == country, Anchor.is_review == user.is_review)

    if language_code:
        query = query.where(Anchor.language_code == language_code)

    sort_column = getattr(Anchor, sort_by)
    query = query.order_by(desc(sort_column))

    count_query = select(func.count()).select_from(Anchor)
    if country:
        count_query = count_query.where(Anchor.country == country, Anchor.is_review == user.is_review)
    if language_code:
        count_query = count_query.where(Anchor.language_code == language_code)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    anchors = result.scalars().all()

    if not anchors:
        return {
            "code": 200,
            "data": {
                "items": [],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            },
        }

    anchor_user_ids = [a.user_id for a in anchors]

    media_result = await db.execute(
        select(Media).where(Media.user_id.in_(anchor_user_ids))
    )
    media_map: dict[int, list] = {}
    for media in media_result.scalars().all():
        media_map.setdefault(media.user_id, []).append(media.to_dict())

    followed_result = await db.execute(
        select(UserFollow.follow_user_id).where(
            UserFollow.user_id == user.user_id,
            UserFollow.follow_user_id.in_(anchor_user_ids),
        )
    )
    followed_ids = set(followed_result.scalars().all())

    liked_result = await db.execute(
        select(UserLike.like_user_id).where(
            UserLike.user_id == user.user_id,
            UserLike.like_user_id.in_(anchor_user_ids),
        )
    )
    liked_ids = set(liked_result.scalars().all())

    items = []
    for anchor in anchors:
        anchor_dict = anchor.to_dict()
        anchor_dict["media_list"] = media_map.get(anchor.user_id, [])
        anchor_dict["is_hot"] = anchor.fans_count > 10000
        anchor_dict["is_new"] = True
        anchor_dict["online_status"] = 1 if anchor.is_review else 0
        anchor_dict["is_followed"] = anchor.user_id in followed_ids
        anchor_dict["is_liked"] = anchor.user_id in liked_ids
        items.append(anchor_dict)

    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
