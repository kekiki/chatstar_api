"""
User information routes.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select

import datetime
from typing import Literal, Optional

from app.database import get_db, get_db_readonly
from app.models import Media, User, UserFollow, UserLike
from app.schemas import GoogleAttribution, GoogleTranslateRequest, DeleteAccountWithAccountPasswordRequest, SetPasswordRequest, UpdateFirebaseTokenRequest, UserInfoRequest
from app.security import current_user, current_user_readonly, get_hash, verify_password
from app.tools import get_http_client


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


@router.post("/user/setPassword")
async def set_password(data: SetPasswordRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Set user password"""
    user.password = get_hash(data.password)
    return {"code": 200, "data": {"message": "Password set successfully"}}

@router.post("/user/deleteAccount")
async def delete_account(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Delete the current user's account."""
    await db.delete(user)
    return {"code": 200, "data": {"message": "Account deleted successfully"}}

@router.post("/user/deleteAccountWithAccountPassword")
async def delete_account_with_account_password(data: DeleteAccountWithAccountPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Delete account with user_id and password."""
    user = await db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.password or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    await db.delete(user)
    return {"code": 200, "data": {"message": "Account deleted successfully"}}

@router.post("/user/updateFirebaseToken")
async def update_firebase_token(data: UpdateFirebaseTokenRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Update user firebase token"""
    user.firebase_token = data.firebase_token
    return {"code": 200, "data": {"message": "update successfully"}}

@router.post("/user/translate")
async def translate(data: GoogleTranslateRequest, user: User = Depends(current_user_readonly)):
    """Translate text using Google Translate"""
    url = f'https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={data.target_language}&dt=t&q={data.text}'
    client = await get_http_client()
    resp = await client.get(
        url,
        content=None,
        headers={"Content-Type": "application/json"}
    )
    print(resp.text)
    return {"code": 200, "data": {"translated_text": resp.text}}


@router.get("/user/getUsers")
async def get_users(
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
    query = select(User).where(User.is_anchor == True, User.is_review == user.is_review)

    if country:
        query = query.where(User.country == country)

    if language_code:
        query = query.where(User.language_code == language_code)

    sort_column = getattr(User, sort_by)
    query = query.order_by(desc(sort_column))

    count_query = select(func.count()).select_from(User).where(User.is_anchor == True, User.is_review == user.is_review)
    if country:
        count_query = count_query.where(User.country == country)
    if language_code:
        count_query = count_query.where(User.language_code == language_code)

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
        anchor_dict["is_new"] = anchor.created_time is not None and anchor.created_time > int((datetime.datetime.now() - datetime.timedelta(days=30)).timestamp())
        anchor_dict["online_status"] = 0
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

@router.get("/user/getUserDetail")
async def get_user_detail(
    data: UserInfoRequest,
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly)
):
    user = await db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"code": 200, "data": user.to_dict()}