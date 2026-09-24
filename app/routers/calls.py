from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from schemas import CreateCallRequest
from app.models import User, Call, Media
from app.models.transaction import ASSET_DIAMOND, ASSET_MATCH_CARD, ASSET_CALL_CARD, TRANSACTION_MATCH, TRANSACTION_CALL 
from app.database import get_db, get_db_readonly
from app.security import current_user, current_user_readonly
from app.tools import add_transaction

import random

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
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a call."""
    if data.user_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot create call to yourself")

    if data.call_type == CALL_TYPE_MATCH:
        if user.match_card_num > 0:
            user.match_card_num = user.match_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_MATCH, db=db)
        elif (user.balance or 0) >= CREATE_MATCH_PRICE:
            user.balance = (user.balance or 0) - CREATE_MATCH_PRICE
            await add_transaction(user, -CREATE_MATCH_PRICE, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_MATCH, db=db)
        else:
            raise HTTPException(status_code=400, detail="Insufficient balance")
    else:
        if user.call_card_num > 0:
            user.call_card_num = user.call_card_num - 1
            await add_transaction(user, -1, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_CALL, db=db)
        elif (user.balance or 0) >= CREATE_CALL_PRICE:
            user.balance = (user.balance or 0) - CREATE_CALL_PRICE
            await add_transaction(user, -CREATE_CALL_PRICE, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_CALL, db=db)
        else:
            raise HTTPException(status_code=400, detail="Insufficient balance")

    media_result = await db.execute(select(Media).where(Media.user_id == data.peer_id, Media.video_type == 1, Media.is_video == True))
    medias = media_result.scalars().all()
    media = random.choice(medias)

    call = Call(
        user_id=user.user_id,
        anchor_id=data.peer_id,
        url=media.url,
        call_type=data.call_type,
    )
    db.add(call)

    return {
        "code": 200,
        "data": call.to_dict(),
    }