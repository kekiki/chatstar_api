"""
Chat routes: history via REST, everything else over WebSocket.
WebSocket is also used by the notification service (balance/order/gift pack pushes).
"""
import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ALGORITHM, SECRET_KEY
from app.database import AsyncSessionLocal, get_db, get_db_readonly
from app.models import ChatMessage, Gift, User
from app.schemas import SendMessageRequest
from app.security import current_user, current_user_readonly
from app.ws_manager import ws_manager

logger = logging.getLogger(__name__)

WS_IDLE_TIMEOUT = 90  # 秒, 超时未收到任何帧则断开连接

router = APIRouter(prefix="/api", tags=["chat"])


async def _build_content(db: AsyncSession, data: SendMessageRequest) -> str:
    """Build the stored content string for each message type."""
    if data.msg_type == "text":
        if not data.content:
            raise HTTPException(400, "content is required for text message")
        return data.content
    if data.msg_type in ("image", "video"):
        if not data.media_url:
            raise HTTPException(400, f"media_url is required for {data.msg_type} message")
        payload = {
            "url": data.media_url,
            "cover": data.media_cover,
        }
        return json.dumps({k: v for k, v in payload.items() if v is not None}, ensure_ascii=False)
    if data.msg_type == "gift":
        if not data.gift_id:
            raise HTTPException(400, "gift_id is required for gift message")
        gift = await db.get(Gift, data.gift_id)
        if not gift:
            raise HTTPException(404, "Gift not found")
        payload = {
            "gift_id": gift.id,
            "gift_name": gift.gift_name,
            "gift_icon": gift.gift_icon,
            "gift_price": gift.gift_price,
            "gift_animation": gift.gift_animation,
            "count": max(1, data.gift_count),
        }
        return json.dumps(payload, ensure_ascii=False)
    raise HTTPException(400, f"unsupported msg_type: {data.msg_type}")


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
    # delivered = await ws_manager.send_to_user(receiver_id, "chat_message", message.to_dict())
    # if delivered:
    #     message.is_delivered = True
    message.is_delivered = True
    return message


@router.post("/chat/send")
async def send_message(
    data: SendMessageRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a one-to-one chat message (text/image/video/gift)."""
    if data.receiver_id == user.user_id:
        raise HTTPException(400, "cannot send message to yourself")
    content = await _build_content(db, data)
    message = await send_chat_message(db, user.user_id, data.receiver_id, data.msg_type, content)
    peer = await db.scalar(select(User).where(User.user_id == data.receiver_id))
    return {"code": 200, "data": message.to_dict() | {"nickname": peer.nickname, "avatar": peer.avatar}}


async def build_conversations(db: AsyncSession, user_id: int) -> list:
    """Build recent conversations with last message and unread count."""
    result = await db.execute(
        select(ChatMessage)
        .where(or_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == user_id))
        .order_by(desc(ChatMessage.id))
        .limit(1000)
    )
    convs = {}
    for m in result.scalars().all():
        peer_id = m.receiver_id if m.sender_id == user_id else m.sender_id
        conv = convs.get(peer_id)
        if not conv:
            conv = {"peer_id": peer_id, "last_message": m.to_dict(), "unread_count": 0}
            convs[peer_id] = conv
        if m.receiver_id == user_id and not m.is_read:
            conv["unread_count"] += 1
    items = list(convs.values())
    if items:
        peer_result = await db.execute(select(User).where(User.user_id.in_([c["peer_id"] for c in items])))
        peers = {u.user_id: u for u in peer_result.scalars().all()}
        for conv in items:
            peer = peers.get(conv["peer_id"])
            if peer:
                conv["nickname"] = peer.nickname
                conv["avatar"] = peer.avatar
                conv["is_anchor"] = peer.is_anchor
    return items


@router.get("/chat/history")
async def chat_history(
    peer_id: int,
    before_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
):
    """Get paginated message history with a peer, newest first."""
    conds = [
        or_(
            and_(ChatMessage.sender_id == user.user_id, ChatMessage.receiver_id == peer_id),
            and_(ChatMessage.sender_id == peer_id, ChatMessage.receiver_id == user.user_id),
        )
    ]
    if before_id:
        conds.append(ChatMessage.id < before_id)
    result = await db.execute(
        select(ChatMessage).where(*conds).order_by(desc(ChatMessage.id)).limit(limit)
    )
    messages = result.scalars().all()
    peer = await db.scalar(select(User).where(User.user_id == peer_id))
    return {"code": 200, "data": [m.to_dict() | {"nickname": peer.nickname, "avatar": peer.avatar} for m in messages]}


def _decode_ws_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub else None
    except (JWTError, ValueError):
        return None


async def _handle_ws_action(user_id: int, raw: str) -> dict:
    """Handle a client action frame; returns an ack payload."""
    try:
        frame = json.loads(raw)
    except ValueError:
        return {"event": "error", "data": {"msg": "invalid json"}}
    action = frame.get("action")
    if action == "ping":
        return {"event": "pong", "data": {}}
    if action == "read_messages":
        data = frame.get("data") or {}
        peer_id = data.get("peer_id")
        if not peer_id:
            return {"event": "error", "data": {"msg": "peer_id is required"}}
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    update(ChatMessage)
                    .where(
                        ChatMessage.receiver_id == user_id,
                        ChatMessage.sender_id == int(peer_id),
                        ChatMessage.is_read.is_(False),
                    )
                    .values(is_read=True)
                )
                await db.commit()
                updated = result.rowcount
            except Exception as e:
                await db.rollback()
                logger.exception("ws read_messages failed")
                return {"event": "error", "data": {"msg": str(e)}}
        return {"event": "read_ack", "data": {"peer_id": int(peer_id), "updated": updated}}
    if action == "get_conversations":
        async with AsyncSessionLocal() as db:
            try:
                items = await build_conversations(db, user_id)
            except Exception as e:
                logger.exception("ws get_conversations failed")
                return {"event": "error", "data": {"msg": str(e)}}
        return {"event": "conversations", "data": items}
    return {"event": "error", "data": {"msg": f"unknown action: {action}"}}


@router.websocket("/ws/connect")
async def ws_connect(websocket: WebSocket, token: str = Query(...)):
    """WebSocket endpoint for chat and notifications.

    Client -> Server actions:
      {"action": "ping"}
      {"action": "read_messages", "data": {"peer_id": 123}}
      {"action": "get_conversations"}
    Server -> Client events:
      init / chat_message / offline_messages / conversations /
      read_ack / pong / error
    """
    user_id = _decode_ws_token(token)
    if not user_id:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await ws_manager.connect(user_id, websocket)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.receiver_id == user_id, ChatMessage.is_delivered.is_(False))
                .order_by(ChatMessage.id.asc())
                .limit(500)
            )
            offline_msgs = result.scalars().all()
            if offline_msgs:
                await websocket.send_text(json.dumps({
                    "event": "offline_messages",
                    "data": [m.to_dict() for m in offline_msgs],
                }, ensure_ascii=False))
                for m in offline_msgs:
                    m.is_delivered = True
                await db.commit()
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=WS_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                logger.info("ws idle timeout, closing user_id=%s", user_id)
                await websocket.close(code=1001)
                break
            ack = await _handle_ws_action(user_id, raw)
            await websocket.send_text(json.dumps(ack, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws connection error user_id=%s", user_id)
    finally:
        await ws_manager.disconnect(user_id, websocket)
