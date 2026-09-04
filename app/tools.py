import httpx
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User, ChatMessage
from app.ws_manager import ws_manager, WS_EVENT_USER_ASSETS_CHANGED, WS_EVENT_SEND_CHAT_MESSAGE

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
    # db.add(message)
    # await db.flush()
    delivered = await ws_manager.send_to_user(receiver_id, WS_EVENT_SEND_CHAT_MESSAGE, message.to_dict())
    if delivered:
        message.is_delivered = True
    return message

async def send_system_chat_message(db: AsyncSession, receiver_id: int, text: str):
    await send_chat_message(db=db, sender_id=999999, receiver_id=receiver_id, msg_type='text', content=text)