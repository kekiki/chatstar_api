"""
Social interaction routes: follow, block, like, report, and list endpoints.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select, and_

from app.database import get_db, get_db_readonly
from app.models import User, UserFollow, UserLike, UserBlock, UserReport
from app.security import current_user, current_user_readonly
from app.routers.tasks import add_task_progress
from app.models.task import TYPE_FOLLOW_USERS

router = APIRouter(prefix="/api", tags=["social"])


# ===================== Follow =====================

@router.post("/user/follow")
async def follow_user(
    target_user_id: int = Query(..., description="User ID to follow"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.user_id == target_user_id:
        return {"code": 400, "msg": "Cannot follow yourself"}
    target = await db.get(User, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    existing = (await db.execute(
        select(UserFollow).where(
            UserFollow.user_id == user.user_id,
            UserFollow.follow_user_id == target_user_id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"code": 400, "msg": "Already followed"}
    db.add(UserFollow(user_id=user.user_id, follow_user_id=target_user_id))
    user.follow_count += 1
    target.fans_count += 1  
    await add_task_progress(db, user.user_id, TYPE_FOLLOW_USERS, 1)
    return {"code": 200, "msg": "success"}

@router.post("/user/unfollow")
async def unfollow_user(
    target_user_id: int = Query(..., description="User ID to unfollow"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserFollow).where(
            UserFollow.user_id == user.user_id,
            UserFollow.follow_user_id == target_user_id,
        )
    )
    follow = result.scalar_one_or_none()
    if not follow:
        return {"code": 400, "msg": "Not followed"}
    await db.delete(follow)
    if user.follow_count > 0:
        user.follow_count -= 1
    target = await db.get(User, target_user_id)
    if target and target.fans_count > 0:
        target.fans_count -= 1
    return {"code": 200, "msg": "success"}


# ===================== Block =====================

@router.post("/user/block")
async def block_user(
    target_user_id: int = Query(..., description="User ID to block"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.user_id == target_user_id:
        return {"code": 400, "msg": "Cannot block yourself"}
    target = await db.get(User, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    existing = (await db.execute(
        select(UserBlock).where(
            UserBlock.user_id == user.user_id,
            UserBlock.block_user_id == target_user_id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"code": 400, "msg": "Already blocked"}
    db.add(UserBlock(user_id=user.user_id, block_user_id=target_user_id))
    return {"code": 200, "msg": "success"}


@router.post("/user/unblock")
async def unblock_user(
    target_user_id: int = Query(..., description="User ID to unblock"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserBlock).where(
            UserBlock.user_id == user.user_id,
            UserBlock.block_user_id == target_user_id,
        )
    )
    block = result.scalar_one_or_none()
    if not block:
        return {"code": 400, "msg": "Not blocked"}
    await db.delete(block)
    return {"code": 200, "msg": "success"}


# ===================== List: My Blocks =====================

@router.get("/user/blocks")
async def get_my_blocks(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    count_query = select(func.count()).select_from(UserBlock).where(UserBlock.user_id == user.user_id)
    total = (await db.execute(count_query)).scalar_one()

    query = (
        select(UserBlock, User)
        .join(User, UserBlock.block_user_id == User.user_id)
        .where(UserBlock.user_id == user.user_id)
        .order_by(desc(UserBlock.created_time))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    items = []
    for block_row, blocked_user in rows:
        d = blocked_user.to_dict()
        d["blocked_at"] = block_row.created_time.isoformat() if block_row.created_time else None
        items.append(d)

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


# ===================== Like =====================

@router.post("/user/like")
async def like_user(
    target_user_id: int = Query(..., description="User ID to like"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.user_id == target_user_id:
        return {"code": 400, "msg": "Cannot like yourself"}
    target = await db.get(User, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    existing = (await db.execute(
        select(UserLike).where(
            UserLike.user_id == user.user_id,
            UserLike.like_user_id == target_user_id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"code": 400, "msg": "Already liked"}
    db.add(UserLike(user_id=user.user_id, like_user_id=target_user_id))
    target.like_count += 1
    return {"code": 200, "msg": "success"}


@router.post("/user/unlike")
async def unlike_user(
    target_user_id: int = Query(..., description="User ID to unlike"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserLike).where(
            UserLike.user_id == user.user_id,
            UserLike.like_user_id == target_user_id,
        )
    )
    like = result.scalar_one_or_none()
    if not like:
        return {"code": 400, "msg": "Not liked"}
    await db.delete(like)
    target = await db.get(User, target_user_id)
    if target and target.like_count > 0:
        target.like_count -= 1
    return {"code": 200, "msg": "success"}


# ===================== Report =====================

@router.post("/user/report")
async def report_user(
    target_user_id: int = Query(..., description="User ID to report"),
    reason: str = Query(default="", max_length=255, description="Report reason"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.user_id == target_user_id:
        return {"code": 400, "msg": "Cannot report yourself"}
    target = await db.get(User, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    db.add(UserReport(user_id=user.user_id, report_user_id=target_user_id, reason=reason))
    return {"code": 200, "msg": "success"}


# ===================== List: My Follows =====================

@router.get("/user/follows")
async def get_my_follows(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    count_query = select(func.count()).select_from(UserFollow).where(UserFollow.user_id == user.user_id)
    total = (await db.execute(count_query)).scalar_one()

    query = (
        select(UserFollow, User)
        .join(User, UserFollow.follow_user_id == User.user_id)
        .where(UserFollow.user_id == user.user_id)
        .order_by(desc(UserFollow.created_time))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    items = []
    for follow_row, followed_user in rows:
        d = followed_user.to_dict()
        d["followed_at"] = follow_row.created_time.isoformat() if follow_row.created_time else None
        items.append(d)

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


# ===================== List: My Fans =====================

@router.get("/user/fans")
async def get_my_fans(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    count_query = select(func.count()).select_from(UserFollow).where(UserFollow.follow_user_id == user.user_id)
    total = (await db.execute(count_query)).scalar_one()

    query = (
        select(UserFollow, User)
        .join(User, UserFollow.user_id == User.user_id)
        .where(UserFollow.follow_user_id == user.user_id)
        .order_by(desc(UserFollow.created_time))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    fan_ids = [f_row.user_id for f_row, _ in rows]

    liked_result = await db.execute(
        select(UserLike.like_user_id).where(
            UserLike.user_id == user.user_id,
            UserLike.like_user_id.in_(fan_ids),
        )
    )
    liked_ids = set(liked_result.scalars().all())

    items = []
    for follow_row, fan_user in rows:
        d = fan_user.to_dict()
        d["fans_at"] = follow_row.created_time.isoformat() if follow_row.created_time else None
        d["is_liked"] = fan_user.user_id in liked_ids
        items.append(d)

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


# ===================== List: Who Liked Me =====================

@router.get("/user/likers")
async def get_my_likers(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    count_query = select(func.count()).select_from(UserLike).where(UserLike.like_user_id == user.user_id)
    total = (await db.execute(count_query)).scalar_one()

    query = (
        select(UserLike, User)
        .join(User, UserLike.user_id == User.user_id)
        .where(UserLike.like_user_id == user.user_id)
        .order_by(desc(UserLike.created_time))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    liker_ids = [l_row.user_id for l_row, _ in rows]

    followed_result = await db.execute(
        select(UserFollow.follow_user_id).where(
            UserFollow.user_id == user.user_id,
            UserFollow.follow_user_id.in_(liker_ids),
        )
    )
    followed_ids = set(followed_result.scalars().all())

    items = []
    for like_row, liker_user in rows:
        d = liker_user.to_dict()
        d["liked_at"] = like_row.created_time.isoformat() if like_row.created_time else None
        d["is_followed"] = liker_user.user_id in followed_ids
        items.append(d)

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
