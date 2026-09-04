from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_readonly
from app.models import Gift, GiftRecord, User
from app.models.transaction import ASSET_DIAMOND, TRANSACTION_GIFT
from app.schemas import SendGiftRequest
from app.security import current_user, current_user_readonly
from app.tools import add_transaction

router = APIRouter(prefix="/api", tags=["gifts"])


@router.get("/user/gifts")
async def get_gifts(user: User = Depends(current_user_readonly), db: AsyncSession = Depends(get_db_readonly)):
    """Get all gifts sorted by price."""
    result = await db.execute(select(Gift).order_by(Gift.gift_price.asc()))
    gifts = result.scalars().all()
    items = [gift.to_dict() for gift in gifts]
    return {"code": 200, "data": items}


@router.post("/user/sendGift")
async def send_gift(
    data: SendGiftRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a gift to another user."""
    if data.user_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot send gift to yourself")

    gift = await db.get(Gift, data.gift_id)
    if not gift:
        raise HTTPException(status_code=404, detail="Gift not found")

    result = await db.execute(select(User).where(User.user_id == data.user_id, User.is_review == user.is_review))
    receiver = result.scalar_one_or_none()
    # receiver = await db.get(User, data.user_id)
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    total_cost = gift.gift_price * data.num
    if (user.balance or 0) < total_cost:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    user.balance = (user.balance or 0) - total_cost
    await add_transaction(user, total_cost, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_GIFT, db=db)

    record = GiftRecord(
        gift_id=gift.id,
        sender_id=user.user_id,
        sender_name=user.nickname,
        sender_avatar=user.avatar,
        receiver_id=receiver.user_id,
    )
    db.add(record)

    return {
        "code": 200,
        "data": {},
    }
