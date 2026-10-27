from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas import CreateCallRequest, RenewCallRequest, HangupCallRequest
from app.models import User, Call, Media
from app.models.transaction import ASSET_DIAMOND, ASSET_MATCH_CARD, ASSET_CALL_CARD, TRANSACTION_MATCH, TRANSACTION_CALL, TRANSACTION_LIVE
from app.database import get_db
from app.security import current_user
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

        if user.match_card_num > 0:
            used_card = True
            user.match_card_num = user.match_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_MATCH, db=db)
        elif (user.balance or 0) >= CREATE_MATCH_PRICE:
            user.balance = (user.balance or 0) - CREATE_MATCH_PRICE
            await add_transaction(user, -CREATE_MATCH_PRICE, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_MATCH, db=db)
        else:
            raise HTTPException(status_code=2001, detail="Insufficient balance")

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
        await send_user_be_followed_or_liked_notification(user, anchor)
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
                "data": call.to_dict() | {'is_ended': call.is_ended, 'is_paid': True},
            }

        call_price = anchor.call_price * 3
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
        await send_user_be_followed_or_liked_notification(user, anchor)
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
        if user.call_card_num > 0:
            used_card = True
            free_seconds = 60
            user.call_card_num = user.call_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_CALL, db=db)
        elif (user.balance or 0) >= anchor.call_price:
            user.balance = (user.balance or 0) - anchor.call_price
            await add_transaction(user, -anchor.call_price, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_CALL, db=db)
        else:
            raise HTTPException(status_code=2001, detail="Insufficient balance")

        media = random.choice(medias)
        call = Call(
            user_id=user.user_id,
            anchor_id=media.user_id,
            url=media.url,
            call_type=data.call_type,
        )
        db.add(call)
        await send_user_be_followed_or_liked_notification(user, anchor)
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

    result = await db.execute(select(User).where(User.user_id == call.anchor_id))
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="User not found")
        
    if call.call_type == CALL_TYPE_LIVE:
        if call.updated_time.second - call.created_time.second < 3:
            live_price = int(anchor.call_price * 3)
            if (user.balance or 0) >= live_price:
                user.balance = (user.balance or 0) - live_price
                await add_transaction(user, -live_price, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_LIVE, db=db)
                call.updated_time = datetime.datetime.now()
            else:
                raise HTTPException(status_code=2001, detail="Insufficient balance")
    else:
        if call.is_ended:
            raise HTTPException(status_code=404, detail="Call did ended")

        if (user.balance or 0) >= anchor.call_price:
            user.balance = (user.balance or 0) - anchor.call_price
            transaction_type = TRANSACTION_MATCH if call.call_type == CALL_TYPE_MATCH else TRANSACTION_CALL
            await add_transaction(user, -anchor.call_price, asset_type=ASSET_DIAMOND, transaction_type=transaction_type, db=db)
            call.updated_time = datetime.datetime.now()
        else:
            raise HTTPException(status_code=2001, detail="Insufficient balance")

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
    if call.is_ended:
        raise HTTPException(status_code=404, detail="Call did ended")

    call.is_ended = True
    call.updated_time = datetime.datetime.now()

    if call.call_type == CALL_TYPE_CALL:
        seconds = (call.updated_time - call.created_time).total_seconds()
        await add_task_progress(db, user.user_id, TYPE_ACTIVE_CALL, int(seconds))

    return {
        "code": 200,
        "data": {},
    }