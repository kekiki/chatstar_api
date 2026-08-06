"""
Chat and notification routes: REST APIs plus a WebSocket endpoint.
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
from app.models import ChatMessage, Gift, Notification, User
from app.models.message import MSG_TYPES
from app.notify import push_notification
from app.schemas import NotifyReadRequest, ReadMessagesRequest, SendMessageRequest
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
            "width": data.media_width,
            "height": data.media_height,
            "duration": data.media_duration,
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
    delivered = await ws_manager.send_to_user(receiver_id, "chat_message", message.to_dict())
    if delivered:
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
    peer = await db.scalar(select(User).where(User.user_id == data.receiver_id))
    if not peer:
        raise HTTPException(404, "Receiver not found")
    content = await _build_content(db, data)
    message = await send_chat_message(db, user.user_id, data.receiver_id, data.msg_type, content)
    return {"code": 200, "data": message.to_dict()}


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
    return {"code": 200, "data": [m.to_dict() for m in messages]}


@router.get("/chat/offline")
async def offline_messages(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pull undelivered (offline) messages and mark them delivered."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.receiver_id == user.user_id, ChatMessage.is_delivered.is_(False))
        .order_by(ChatMessage.id.asc())
        .limit(500)
    )
    messages = result.scalars().all()
    for m in messages:
        m.is_delivered = True
    return {"code": 200, "data": [m.to_dict() for m in messages]}


@router.post("/chat/read")
async def read_messages(
    data: ReadMessagesRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all messages from a peer as read."""
    result = await db.execute(
        update(ChatMessage)
        .where(
            ChatMessage.receiver_id == user.user_id,
            ChatMessage.sender_id == data.peer_id,
            ChatMessage.is_read.is_(False),
        )
        .values(is_read=True)
    )
    return {"code": 200, "data": {"updated": result.rowcount}}


@router.get("/chat/conversations")
async def conversations(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
):
    """List recent conversations with last message and unread count."""
    result = await db.execute(
        select(ChatMessage)
        .where(or_(ChatMessage.sender_id == user.user_id, ChatMessage.receiver_id == user.user_id))
        .order_by(desc(ChatMessage.id))
        .limit(1000)
    )
    convs = {}
    for m in result.scalars().all():
        peer_id = m.receiver_id if m.sender_id == user.user_id else m.sender_id
        conv = convs.get(peer_id)
        if not conv:
            conv = {"peer_id": peer_id, "last_message": m.to_dict(), "unread_count": 0}
            convs[peer_id] = conv
        if m.receiver_id == user.user_id and not m.is_read:
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
    return {"code": 200, "data": items}


@router.get("/notify/list")
async def notify_list(
    notify_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, le=100),
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
):
    """List notifications for the current user, newest first."""
    conds = [Notification.user_id == user.user_id]
    if notify_type:
        conds.append(Notification.notify_type == notify_type)
    total = await db.scalar(select(func.count(Notification.id)).where(*conds))
    result = await db.execute(
        select(Notification)
        .where(*conds)
        .order_by(desc(Notification.id))
        .offset((page - 1) * size)
        .limit(size)
    )
    unread = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.user_id, Notification.is_read.is_(False)
        )
    )
    return {
        "code": 200,
        "data": {
            "total": total or 0,
            "unread_count": unread or 0,
            "items": [n.to_dict() for n in result.scalars().all()],
        },
    }


@router.post("/notify/read")
async def read_notifications(
    data: NotifyReadRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark notifications as read; empty ids marks all as read."""
    conds = [Notification.user_id == user.user_id, Notification.is_read.is_(False)]
    if data.ids:
        conds.append(Notification.id.in_(data.ids))
    result = await db.execute(update(Notification).where(*conds).values(is_read=True))
    return {"code": 200, "data": {"updated": result.rowcount}}


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
    if action == "send_chat_message":
        data = frame.get("data") or {}
        try:
            req = SendMessageRequest(**data)
        except Exception as e:
            return {"event": "error", "data": {"msg": f"invalid message: {e}"}}
        if req.receiver_id == user_id:
            return {"event": "error", "data": {"msg": "cannot send message to yourself"}}
        async with AsyncSessionLocal() as db:
            try:
                peer = await db.scalar(select(User).where(User.user_id == req.receiver_id))
                if not peer:
                    return {"event": "error", "data": {"msg": "receiver not found"}}
                content = await _build_content(db, req)
                message = await send_chat_message(db, user_id, req.receiver_id, req.msg_type, content)
                ack_data = message.to_dict()
                await db.commit()
            except HTTPException as e:
                return {"event": "error", "data": {"msg": e.detail}}
            except Exception as e:
                await db.rollback()
                logger.exception("ws send_chat_message failed")
                return {"event": "error", "data": {"msg": str(e)}}
        return {"event": "message_ack", "data": ack_data}
    return {"event": "error", "data": {"msg": f"unknown action: {action}"}}


@router.websocket("/ws/connect")
async def ws_connect(websocket: WebSocket, token: str = Query(...)):
    """WebSocket endpoint for chat and notifications.

    Client -> Server frames: {"action": "ping"} / {"action": "send_message", "data": {...}}
    Server -> Client events: init / chat_message / notification / message_ack / pong / error
    """
    user_id = _decode_ws_token(token)
    if not user_id:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await ws_manager.connect(user_id, websocket)
    try:
        async with AsyncSessionLocal() as db:
            offline_count = await db.scalar(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.receiver_id == user_id, ChatMessage.is_delivered.is_(False)
                )
            )
            unread_notify = await db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id, Notification.is_read.is_(False)
                )
            )
        await websocket.send_text(json.dumps({
            "event": "init",
            "data": {
                "user_id": user_id,
                "offline_message_count": offline_count or 0,
                "unread_notify_count": unread_notify or 0,
            },
        }))
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
