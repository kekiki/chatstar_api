from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.schemas import CreateCallRequest, RenewCallRequest, HangupCallRequest
from app.models import User, Call, Media
from app.models.transaction import ASSET_DIAMOND, ASSET_MATCH_CARD, ASSET_CALL_CARD, TRANSACTION_MATCH, TRANSACTION_CALL, TRANSACTION_LIVE, TRANSACTION_REFUND
from app.database import get_db, get_db_readonly
from app.security import current_user, current_user_readonly
from app.tools import add_transaction, send_user_be_followed_or_liked_notification
from app.routers.tasks import add_task_progress
from app.models.task import TYPE_MATCH_TIMES, TYPE_ACTIVE_CALL

import random
import datetime

router = APIRouter(prefix="/api", tags=["calls"])

CREATE_MATCH_PRICE = 400

CALL_TYPE_CALL=0
CALL_TYPE_AIB=1
CALL_TYPE_MATCH=2
CALL_TYPE_LIVE=3

@router.post("/call/create")
async def createCall(
    data: CreateCallRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a call."""

    used_card = False
    call_price = 0
    free_seconds = 0
    if data.call_type == CALL_TYPE_MATCH:
        media_result = await db.execute(select(Media).where(Media.video_type == 1, Media.is_video == True))
        medias = media_result.scalars().all()
        if len(medias) <= 0:
            raise HTTPException(status_code=400, detail="Create match call failed")
    
        await add_task_progress(db, user.user_id, TYPE_MATCH_TIMES, 1)

        if (user.match_card_num or 0) > 0:
            used_card = True
            user.match_card_num = user.match_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_MATCH, db=db)
        elif (user.balance or 0) >= CREATE_MATCH_PRICE:
            user.balance = (user.balance or 0) - CREATE_MATCH_PRICE
            await add_transaction(user, -CREATE_MATCH_PRICE, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_MATCH, db=db)
        else:
            return {"code": 2001, "msg": "Insufficient balance"}

        media = random.choice(medias)
        result = await db.execute(select(User).where(User.user_id == media.user_id))
        anchor = result.scalar_one_or_none()
        if not anchor:
            raise HTTPException(status_code=404, detail="User not found")

        call_price = anchor.call_price
        free_seconds = 20
        call = Call(
            user_id=user.user_id,
            anchor_id=media.user_id,
            url=media.url,
            call_type=data.call_type,
        )
        db.add(call)
        await send_user_be_followed_or_liked_notification(user, anchor, db)
        await db.flush()

        return {
            "code": 200,
            "data": call.to_dict() | {'used_card': used_card, 'call_price': call_price, 'free_seconds': free_seconds},
        }
        
    elif data.call_type == CALL_TYPE_LIVE:
        result = await db.execute(select(User).where(User.user_id == data.peer_id))
        anchor = result.scalar_one_or_none()
        if not anchor:
            raise HTTPException(status_code=404, detail="User not found")

        call_price = anchor.call_price * 3
        recent_call_time = datetime.datetime.now() - datetime.timedelta(hours=6)
        result = await db.execute(
            select(Call)
            .where(
                Call.user_id == user.user_id,
                Call.anchor_id == data.peer_id,
                Call.call_type == data.call_type,
                Call.created_time > recent_call_time,
            )
            .order_by(Call.created_time.desc())
            .limit(1)
        )
        call = result.scalar_one_or_none()
        if call:
            return {
                "code": 200,
                "data": call.to_dict() | {'call_price': call_price},
            }

        free_seconds = 30
        media_result = await db.execute(select(Media).where(Media.user_id == data.peer_id, Media.video_type != 0, Media.is_video == True))
        medias = media_result.scalars().all()
        if len(medias) <= 0:
            raise HTTPException(status_code=400, detail="Create live call failed")

        media = random.choice(medias)
        call = Call(
            user_id=user.user_id,
            anchor_id=media.user_id,
            url=media.url,
            call_type=data.call_type,
        )
        db.add(call)
        await send_user_be_followed_or_liked_notification(user, anchor, db)
        await db.flush()

        return {
            "code": 200,
            "data": call.to_dict() | {'call_price': call_price, 'free_seconds': free_seconds},
        }
    
    else:
        result = await db.execute(select(User).where(User.user_id == data.peer_id))
        anchor = result.scalar_one_or_none()
        if not anchor:
            raise HTTPException(status_code=404, detail="User not found")

        media_result = await db.execute(select(Media).where(Media.user_id == data.peer_id, Media.video_type == 1, Media.is_video == True))
        medias = media_result.scalars().all()
        if len(medias) <= 0:
            raise HTTPException(status_code=400, detail="Create call failed")

        call_price = anchor.call_price
        is_paid = False
        if (user.call_card_num or 0) > 0:
            used_card = True
            free_seconds = 60
            user.call_card_num = user.call_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_CALL, db=db)
        elif (user.balance or 0) >= anchor.call_price:
            is_paid = True
            user.balance = (user.balance or 0) - anchor.call_price
            await add_transaction(user, -anchor.call_price, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_CALL, db=db)
        else:
            return {"code": 2001, "msg": "Insufficient balance"}

        media = random.choice(medias)
        call = Call(
            user_id=user.user_id,
            anchor_id=media.user_id,
            url=media.url,
            call_type=data.call_type,
            is_paid=is_paid,
        )
        db.add(call)
        await send_user_be_followed_or_liked_notification(user, anchor, db)
        await db.flush()

        return {
            "code": 200,
            "data": call.to_dict() | {'used_card': used_card, 'call_price': call_price, 'free_seconds': free_seconds},
        }


@router.post("/call/renew")
async def renewCall(
    data: RenewCallRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Call).where(Call.id == data.call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    result = await db.execute(select(User).where(User.user_id == call.anchor_id))
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
        
    if call.call_type == CALL_TYPE_LIVE:
        if (call.updated_time - call.created_time).total_seconds() < 30:
            live_price = int(anchor.call_price * 3)
            if (user.balance or 0) >= live_price:
                user.balance = (user.balance or 0) - live_price
                await add_transaction(user, -live_price, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_LIVE, db=db)
                call.updated_time = datetime.datetime.now()
                call.is_paid = True
            else:
                return {"code": 2001, "msg": "Insufficient balance"}
    else:
        if call.is_ended:
            raise HTTPException(status_code=404, detail="Call did ended")

        if (user.balance or 0) >= anchor.call_price:
            user.balance = (user.balance or 0) - anchor.call_price
            transaction_type = TRANSACTION_MATCH if call.call_type == CALL_TYPE_MATCH else TRANSACTION_CALL
            await add_transaction(user, -anchor.call_price, asset_type=ASSET_DIAMOND, transaction_type=transaction_type, db=db)
            call.updated_time = datetime.datetime.now()
            call.is_paid = True
        else:
            return {"code": 2001, "msg": "Insufficient balance"}

    return {
        "code": 200,
        "data": {},
    }

@router.post("/call/start")
async def startCall(
    data: RenewCallRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Call).where(Call.id == data.call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    call.created_time = datetime.datetime.now()
    return {
        "code": 200,
        "data": {},
    }

@router.post("/call/end")
async def endCall(
    data: HangupCallRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Call).where(Call.id == data.call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Permission denied")
    if call.is_ended:
        raise HTTPException(status_code=404, detail="Call did ended")

    call.is_ended = True
    call.updated_time = datetime.datetime.now()
    duration = (call.updated_time - call.created_time).total_seconds()

    if call.call_type == CALL_TYPE_CALL:
        await add_task_progress(db, user.user_id, TYPE_ACTIVE_CALL, int(duration))

    if not data.user_hangup and call.is_paid and duration < 30:
        result = await db.execute(select(User).where(User.user_id == call.anchor_id))
        anchor = result.scalar_one_or_none()
        if not anchor:
            raise HTTPException(status_code=404, detail="Anchor not found")

        await add_transaction(user, anchor.call_price, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_REFUND, db=db)
        
    return {
        "code": 200,
        "data": {},
    }


@router.get("/call/records")
async def get_call_records(
    user_id: Optional[int] = Query(default=None, description="User ID, defaults to the current user"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
):
    """Get paginated call records for a user, sorted by created_time desc.

    Only the current user's own records can be queried; passing another
    user's ID is rejected.
    """
    target_user_id = user_id if user_id is not None else user.user_id
    if target_user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    base_query = select(Call).where(Call.user_id == target_user_id, Call.call_type != CALL_TYPE_LIVE)#排除直播
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(Call.created_time.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    calls = result.scalars().all()

    # 批量取对端用户信息，避免 N+1 查询
    peer_ids = list({call.anchor_id for call in calls if call.anchor_id})
    peers = {}
    if peer_ids:
        peer_result = await db.execute(select(User).where(User.user_id.in_(peer_ids)))
        peers = {peer.user_id: peer for peer in peer_result.scalars().all()}

    media_result = await db.execute(
        select(Media).where(Media.user_id.in_(peer_ids))
    )
    media_map: dict[int, list] = {}
    for media in media_result.scalars().all():
        media_map.setdefault(media.user_id, []).append(media)

    items = []
    for call in calls:
        peer = peers.get(call.anchor_id)
        duration_seconds = 0
        if call.is_ended and call.created_time and call.updated_time:
            duration_seconds = max(0, int((call.updated_time - call.created_time).total_seconds()))

        live_list = []
        for m in media_map.get(peer.user_id, []):
            if m.is_video and m.video_type != 0:
                live_list.append(m.to_dict())
        is_live_status = len(live_list) > 0 and peer.fans_count % 2 == 0 

        if user.is_review:
            online_status = 1
        else:
            if is_live_status:
                online_status = 2 
            else:
                online_status = 1 if peer.is_review else 0

        items.append({
            "call_id": call.id,
            "peer_id": call.anchor_id,
            "call_type": call.call_type,
            "is_ended": call.is_ended,
            "is_paid": call.is_paid,
            "duration_seconds": duration_seconds,
            "created_time": int(call.created_time.timestamp()) if call.created_time else None,
            "updated_time": int(call.updated_time.timestamp()) if call.updated_time else None,
            "peer_info": {
                "user_id": peer.user_id,
                "nickname": peer.nickname,
                "avatar": peer.avatar,
                "online_status": online_status,
            } if peer else None,
        })

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