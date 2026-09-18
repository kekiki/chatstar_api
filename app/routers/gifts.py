import asyncio
import logging
import random

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db, get_db_readonly
from app.models import Gift, GiftRecord, User
from app.models.transaction import ASSET_DIAMOND, TRANSACTION_GIFT
from app.schemas import SendGiftRequest
from app.security import current_user, current_user_readonly
from app.tools import add_transaction, send_chat_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["gifts"])

GIFT_REPLY_MESSAGES = [
    "Thanks",
    "Thank you",
    "Thanks❤️",
    "Thank you❤️",
    "Thanks😘",
    "Thank you😘",
    "Thank you very much",
    "🌹🌹🌹",
    "Thank you for your gift.",
    "Thanks for your present.",
    "❤️❤️❤️❤️❤️❤️❤️❤️❤️❤️",
    "😘😘😘😘😘😘"
]

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
    background_tasks: BackgroundTasks,
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
    await add_transaction(user, -total_cost, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_GIFT, db=db)

    record = GiftRecord(
        gift_id=gift.id,
        sender_id=user.user_id,
        sender_name=user.nickname,
        sender_avatar=user.avatar,
        receiver_id=receiver.user_id,
        gift_name=gift.gift_name,
        gift_icon=gift.gift_icon,
        gift_price=gift.gift_price,
    )
    db.add(record)
    await db.flush()

    gift_sender_id = user.user_id
    anchor_id = receiver.user_id

    await db.commit()

    background_tasks.add_task(background_chat_task, sender_id=anchor_id, receiver_id=gift_sender_id)

    return {
        "code": 200,
        "data": {},
    }


async def background_chat_task(sender_id: int, receiver_id: int):
    try:
        delay_sec = random.uniform(5, 20)
        await asyncio.sleep(delay_sec)

        reply_text = random.choice(GIFT_REPLY_MESSAGES)
        async with AsyncSessionLocal() as db:
            await send_chat_message(db=db, sender_id=sender_id, receiver_id=receiver_id, msg_type='text', content=reply_text)
            await db.commit()
    except Exception as e:
        logger.exception("sendGift background chat task failed: %s", e)
