from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas import CreateCallRequest, RenewCallRequest, HangupCallRequest
from app.models import User, Call, Media
from app.models.transaction import ASSET_DIAMOND, ASSET_MATCH_CARD, ASSET_CALL_CARD, TRANSACTION_MATCH, TRANSACTION_CALL 
from app.database import get_db, get_db_readonly
from app.security import current_user, current_user_readonly
from app.tools import add_transaction

import random
import datetime

router = APIRouter(prefix="/api", tags=["calls"])

CREATE_MATCH_PRICE = 400
CREATE_CALL_PRICE = 4000

CALL_TYPE_CALL=0
CALL_TYPE_AIV=1
CALL_TYPE_AIB=2
CALL_TYPE_MATCH=3

@router.post("/call/create")
async def createCall(
    data: CreateCallRequest,
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly)
):
    """Create a call."""
    if data.peer_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot create call to yourself")

    if data.call_type == CALL_TYPE_MATCH:
        if user.match_card_num > 0:
            user.match_card_num = user.match_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_MATCH, db=db)
        elif (user.balance or 0) >= CREATE_MATCH_PRICE:
            user.balance = (user.balance or 0) - CREATE_MATCH_PRICE
            await add_transaction(user, -CREATE_MATCH_PRICE, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_MATCH, db=db)
        else:
            raise HTTPException(status_code=2001, detail="Insufficient balance")

        media_result = await db.execute(select(Media).where(Media.video_type == 1, Media.is_video == True))
    else:
        if user.call_card_num > 0:
            user.call_card_num = user.call_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_CALL, db=db)
        elif (user.balance or 0) >= CREATE_CALL_PRICE:
            user.balance = (user.balance or 0) - CREATE_CALL_PRICE
            await add_transaction(user, -CREATE_CALL_PRICE, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_CALL, db=db)
        else:
            raise HTTPException(status_code=2001, detail="Insufficient balance")
        
        media_result = await db.execute(select(Media).where(Media.user_id == data.peer_id, Media.video_type == 1, Media.is_video == True))
    
    medias = media_result.scalars().all()
    if len(medias) <= 0:
        raise HTTPException(status_code=400, detail="Create call failed")

    media = random.choice(medias)
    call = Call(
        user_id=user.user_id,
        anchor_id=media.user_id,
        url=media.url,
        call_type=data.call_type,
    )
    db.add(call)
    await db.flush()

    return {
        "code": 200,
        "data": call.to_dict(),
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
    if call.is_ended:
        raise HTTPException(status_code=404, detail="Call did ended")

    if (user.balance or 0) >= CREATE_CALL_PRICE:
        user.balance = (user.balance or 0) - CREATE_CALL_PRICE
        transaction_type = TRANSACTION_MATCH if call.call_type == CALL_TYPE_MATCH else CALL_TYPE_CALL
        await add_transaction(user, -CREATE_CALL_PRICE, asset_type=ASSET_DIAMOND, transaction_type=transaction_type, db=db)
    else:
        raise HTTPException(status_code=2001, detail="Insufficient balance")

    call.updated_time = datetime.datetime.now()

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

    return {
        "code": 200,
        "data": {},
    }