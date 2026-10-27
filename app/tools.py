import httpx
import uuid
import random

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import User, ChatMessage, UserFollow, UserLike
from app.ws_manager import ws_manager, WS_EVENT_USER_ASSETS_CHANGED, WS_EVENT_SEND_CHAT_MESSAGE, WS_EVENT_NEW_USER_REWARD, WS_EVENT_USER_BE_FOLLOWED, WS_EVENT_USER_BE_LIKED

_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(verify=False, timeout=30.0)
    return _http_client


async def add_transaction(user: User, amount: int, asset_type: int, transaction_type: int, db: AsyncSession):
    from app.models import Transaction

    transaction = Transaction(user_id=user.user_id, amount=amount, asset_type=asset_type, transaction_type=transaction_type)
    db.add(transaction)
    await send_userinfo_assets_notification(user)

async def send_userinfo_assets_notification(user: User):
    data = {
        "balance": user.balance,
        "is_vip": user.is_vip,
        "vip_expire_time": user.vip_expire_time,
        "call_card_num": user.call_card_num,
        "match_card_num": user.match_card_num,
        "chat_card_num": user.chat_card_num,
        "total": user.total,
    }
    await ws_manager.send_to_user(user_id=user.user_id, event=WS_EVENT_USER_ASSETS_CHANGED, data=data)

async def send_new_user_reward_notification(user: User):
    data = {
        "balance": user.balance,
        "call_card_num": user.call_card_num,
        "match_card_num": user.match_card_num,
        "chat_card_num": user.chat_card_num,
    }
    await ws_manager.send_to_user(user_id=user.user_id, event=WS_EVENT_NEW_USER_REWARD, data=data)

async def send_user_be_followed_or_liked_notification(fromUser: User, toUser: User, db: AsyncSession):
    if random.random() < 0.5:
        followed_result = await db.execute(
            select(UserFollow.follow_user_id).where(
                UserFollow.user_id == toUser.user_id,
                UserFollow.follow_user_id == fromUser.user_id,
            )
        )
        followed_ids = set(followed_result.scalars().all())
        if fromUser.user_id not in followed_ids:
            toUser.follow_count += 1
            fromUser.fans_count += 1
            db.add(UserFollow(user_id=toUser.user_id, follow_user_id=fromUser.user_id))
            data = {"fans_count": fromUser.fans_count}
            await ws_manager.send_to_user(user_id=fromUser.user_id, event=WS_EVENT_USER_BE_FOLLOWED, data=data)
    else:
        liked_result = await db.execute(
            select(UserLike.like_user_id).where(
                UserLike.user_id == toUser.user_id,
                UserLike.like_user_id == fromUser.user_id,
            )
        )
        liked_ids = set(liked_result.scalars().all())
        if fromUser.user_id not in liked_ids:
            fromUser.like_count += 1
            db.add(UserLike(user_id=toUser.user_id, like_user_id=fromUser.user_id))
            data = {"like_count": fromUser.like_count}
            await ws_manager.send_to_user(user_id=fromUser.user_id, event=WS_EVENT_USER_BE_LIKED, data=data)

async def send_chat_message(
    db: AsyncSession,
    sender_id: int,
    receiver_id: int,
    msg_type: str,
    content: str,
) -> ChatMessage:
    """Persist a message and push it to the receiver over WebSocket if online."""
    message = ChatMessage(
        msg_no=uuid.uuid4().hex,
        sender_id=sender_id,
        receiver_id=receiver_id,
        msg_type=msg_type,
        content=content,
    )
    db.add(message)
    await db.flush()
    delivered = await ws_manager.send_to_user(receiver_id, WS_EVENT_SEND_CHAT_MESSAGE, message.to_dict() | {'user_id': sender_id})
    if delivered:
        message.is_delivered = True
    return message

async def send_system_chat_message(db: AsyncSession, receiver_id: int, text: str):
    await send_chat_message(db=db, sender_id=999999, receiver_id=receiver_id, msg_type='text', content=text)