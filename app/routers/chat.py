"""
Chat routes: history via REST, everything else over WebSocket.
WebSocket is also used by the notification service (balance/order/gift pack pushes).
"""
import asyncio
import json
import logging
import uuid
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, BackgroundTasks
from jose import JWTError, jwt
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ALGORITHM, SECRET_KEY, IS_DEBUG
from app.database import AsyncSessionLocal, get_db, get_db_readonly
from app.models import Gift, User, ChatMessage
from app.models.transaction import ASSET_DIAMOND, ASSET_CHAT_CARD, TRANSACTION_CHAT, TRANSACTION_NEW_REWARD, ASSET_CALL_CARD, ASSET_MATCH_CARD
from app.schemas import SendMessageRequest
from app.security import current_user, current_user_readonly
from app.tools import add_transaction, send_chat_message, send_userinfo_assets_notification, send_new_user_reward_notification, send_new_user_welcome_notification
from app.ws_manager import ws_manager
from app.greq_client import groq_client

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
            "media_url": data.media_url,
            "media_cover": data.media_cover,
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


CHAT_MESSAGE_DIAMOND_COST = 10


@router.post("/chat/send")
async def send_message(
    data: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a one-to-one chat message (text/image/video/gift)."""
    if data.receiver_id == user.user_id:
        raise HTTPException(400, "cannot send message to yourself")

    if (user.chat_card_num or 0) > 0:
        user.chat_card_num -= 1
        await add_transaction(user, -1, asset_type=ASSET_CHAT_CARD, transaction_type=TRANSACTION_CHAT, db=db)
    elif (user.balance or 0) >= CHAT_MESSAGE_DIAMOND_COST:
        user.balance -= CHAT_MESSAGE_DIAMOND_COST
        await add_transaction(user, -CHAT_MESSAGE_DIAMOND_COST, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_CHAT, db=db)
    else:
        raise HTTPException(2001, "Insufficient balance")

    content = await _build_content(db, data)
    message = ChatMessage(
        msg_no=uuid.uuid4().hex,
        sender_id=user.user_id,
        receiver_id=data.receiver_id,
        msg_type=data.msg_type,
        content=content,
    )

    db.add(message)
    await db.flush()

    sender_id = user.user_id
    receiver_id = data.receiver_id
    message_dict = message.to_dict()
    before_id = message.id

    await db.commit()

    # 所有消息类型均触发AI异步回复(图片/视频/礼物转成事件描述让AI自然反应)
    background_tasks.add_task(background_chat_task, sender_id=sender_id, receiver_id=receiver_id, content=content, before_id=before_id, msg_type=data.msg_type)

    return {"code": 200, "data": message_dict}


def _readable_profile_field(value: Optional[str], limit: int = 200) -> str:
    """Normalize a free-form profile field (plain text or JSON) to readable text."""
    if not value or not value.strip():
        return ""
    text = value.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            text = ", ".join(str(x) for x in parsed if x)
        elif isinstance(parsed, dict):
            text = ", ".join(str(v) for v in parsed.values() if v)
    except (ValueError, TypeError):
        pass
    return text[:limit].strip()


def _build_role_desc(anchor: User) -> str:
    """Build the AI anchor persona from her profile."""
    parts = [f"You are {anchor.nickname or 'a lovely streamer'}, a warm and friendly {anchor.age or 22}-year-old female streamer on a global social app."]
    if anchor.country:
        parts.append(f"You live in {anchor.country}.")
    tags = _readable_profile_field(anchor.tags)
    if tags:
        parts.append(f"Your personality and interests: {tags}.")
    info = _readable_profile_field(anchor.info)
    if info:
        parts.append(f"Your self-introduction: {info}.")
    return " ".join(parts)


def _build_ai_input(msg_type: str, content: str) -> str:
    """把收到的消息转成 AI 对话输入; 非文本消息转为事件描述。"""
    if msg_type == "text":
        return content
    if msg_type == "gift":
        gift_desc = ""
        try:
            payload = json.loads(content)
            if isinstance(payload, dict) and payload.get("gift_name"):
                count = payload.get("count") or 1
                gift_desc = f" {payload['gift_name']}" + (f" x{count}" if isinstance(count, int) and count > 1 else "")
        except (ValueError, TypeError):
            pass
        return f"(He just sent you a virtual gift{gift_desc} in your chat. React sweetly surprised and thank him warmly, maybe tease him a little.)"
    if msg_type == "image":
        return "(He just sent you a photo in your chat. React warmly with playful curiosity or a sweet compliment, and ask him about it.)"
    if msg_type == "video":
        return "(He just sent you a short video in your chat. React warmly with playful curiosity and ask him about it.)"
    return content


async def background_chat_task(sender_id: int, receiver_id: int, content: str, before_id: int, msg_type: str = "text"):
    try:
        delay_sec = random.uniform(5, 30)
        await asyncio.sleep(delay_sec)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.user_id == receiver_id))
            anchor = result.scalar_one_or_none()
            if not anchor:
                # logger.warning("AI reply skipped, receiver not found user_id=%s", receiver_id)
                return

            if anchor.is_review:
                # logger.warning("AI reply skipped, receiver offline user_id=%s", receiver_id)
                return

            lang_code = anchor.language_code
            role_desc = _build_role_desc(anchor)

            conds = [
                or_(
                    and_(ChatMessage.sender_id == sender_id, ChatMessage.receiver_id == receiver_id),
                    and_(ChatMessage.sender_id == receiver_id, ChatMessage.receiver_id == sender_id),
                ),
                ChatMessage.id < before_id,
            ]
            result = await db.execute(
                select(ChatMessage).where(*conds).order_by(desc(ChatMessage.id)).limit(6)
            )
            messages = result.scalars().all()
            if len(messages) > 0 and messages[-1].sender_id == sender_id:
                logger.warning("AI reply skipped, last message is yours")
                return

            history_msgs = []
            for r in messages:
                if r.msg_type == 'text':
                    role = 'assistant' if r.sender_id != sender_id else 'user'
                    history_msgs.append({"role": role, "content": r.content})

            ai_input = _build_ai_input(msg_type, content)
            reply_text = await groq_client.chat_endpoint(content=ai_input, lang_code=lang_code, role_desc=role_desc, history_messages=history_msgs)

            if reply_text and len(reply_text) > 0:
                await send_chat_message(db=db, sender_id=receiver_id, receiver_id=sender_id, msg_type='text', content=reply_text)
            await db.commit()
    except Exception as e:
        logger.exception("chat AI reply background task failed: %s", e)


# ---------- 话术任务: 用户 WS 在线时由随机主播主动发消息引导聊天 ----------

SOLICIT_FIRST_DELAY_RANGE = (8, 15)       # 连接后首条消息延迟(秒)
SOLICIT_INITIAL_INTERVAL_RANGE = (10, 20) # 初始发送间隔(秒)
SOLICIT_INTERVAL_GROWTH = 1.6             # 间隔增长系数: 连接越久频率越低
SOLICIT_MAX_INTERVAL = 300                # 最大间隔(秒)
SOLICIT_RECENT_ANCHOR_LIMIT = 5           # 短期内不重复选取的主播数

SOLICIT_OPENERS = [
    "You just noticed a fan you like is online. Send him a short sweet hello and invite him to chat with you now.",
    "You are a little bored tonight and want someone fun to talk to. Text a fan a playful message to start a chat.",
    "You saw a fan online you'd love to know better. Send him a warm, slightly flirty message to catch his attention.",
    "You want a fan to notice you. Send an inviting, teasingly sweet message to draw him into a chat.",
]

# 每个用户一个话术任务, 多端连接只启动一个
_solicit_tasks: dict = {}


async def _pick_random_anchor(db: AsyncSession, user_id: int, recent_anchor_ids: set) -> Optional[User]:
    """随机选取一位在线池中的主播, 尽量避开近期已发过的。"""
    conds = [User.is_anchor.is_(True), User.is_review.is_(False), User.user_id != user_id]
    if recent_anchor_ids:
        conds.append(User.user_id.not_in(recent_anchor_ids))
    result = await db.execute(select(User).where(*conds).order_by(func.random()).limit(1))
    anchor = result.scalars().first()
    if anchor or not recent_anchor_ids:
        return anchor
    # 候选不足时放宽"近期已发"限制
    result = await db.execute(
        select(User)
        .where(User.is_anchor.is_(True), User.is_review.is_(False), User.user_id != user_id)
        .order_by(func.random())
        .limit(1)
    )
    return result.scalars().first()


async def solicit_chat_task(user_id: int):
    """周期性给在线用户发送主播引导消息, 间隔随连接时长递增。"""
    recent_anchor_ids: set = set()
    interval = random.uniform(*SOLICIT_INITIAL_INTERVAL_RANGE)
    try:
        await asyncio.sleep(random.uniform(*SOLICIT_FIRST_DELAY_RANGE))
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(User).where(User.user_id == user_id))
                    user = result.scalar_one_or_none()
                    # 用户不存在/审核模式/用户本身是主播时终止任务
                    if not user or user.is_review or user.is_anchor:
                        return
                    anchor = await _pick_random_anchor(db, user_id, recent_anchor_ids)
                    if anchor:
                        # 注意: commit 会使 ORM 对象过期(expire_on_commit), 之后不可再访问其属性,
                        # 所以先取好所有需要的字段
                        anchor_user_id = anchor.user_id
                        anchor_lang = anchor.language_code
                        text = await groq_client.chat_endpoint(
                            content=random.choice(SOLICIT_OPENERS),
                            # 主播资料是什么语言就一直用什么语言发消息
                            lang_code=anchor_lang,
                            role_desc=_build_role_desc(anchor),
                            history_messages=[],
                        )
                        if text:
                            await send_chat_message(db=db, sender_id=anchor_user_id, receiver_id=user_id, msg_type='text', content=text)
                            await db.commit()
                            recent_anchor_ids.add(anchor_user_id)
                            if len(recent_anchor_ids) > SOLICIT_RECENT_ANCHOR_LIMIT:
                                recent_anchor_ids.pop()
            except Exception as e:
                # 单轮失败不终止任务, 等下一轮重试
                logger.exception("solicit chat round failed user_id=%s: %s", user_id, e)
            interval = min(interval * SOLICIT_INTERVAL_GROWTH, SOLICIT_MAX_INTERVAL)
            await asyncio.sleep(random.uniform(interval * 0.8, interval * 1.2))
    except asyncio.CancelledError:
        pass


# async def build_conversations(db: AsyncSession, user_id: int) -> list:
#     """Build recent conversations with last message and unread count."""
#     result = await db.execute(
#         select(ChatMessage)
#         .where(or_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == user_id))
#         .order_by(desc(ChatMessage.id))
#         .limit(1000)
#     )
#     convs = {}
#     for m in result.scalars().all():
#         peer_id = m.receiver_id if m.sender_id == user_id else m.sender_id
#         conv = convs.get(peer_id)
#         if not conv:
#             conv = {"peer_id": peer_id, "last_message": m.to_dict(), "unread_count": 0}
#             convs[peer_id] = conv
#         if m.receiver_id == user_id and not m.is_read:
#             conv["unread_count"] += 1
#     items = list(convs.values())
#     if items:
#         peer_result = await db.execute(select(User).where(User.user_id.in_([c["peer_id"] for c in items])))
#         peers = {u.user_id: u for u in peer_result.scalars().all()}
#         for conv in items:
#             peer = peers.get(conv["peer_id"])
#             if peer:
#                 conv["nickname"] = peer.nickname
#                 conv["avatar"] = peer.avatar
#                 conv["is_anchor"] = peer.is_anchor
#     return items


# @router.get("/chat/history")
# async def chat_history(
#     peer_id: int,
#     before_id: Optional[int] = None,
#     limit: int = Query(50, le=200),
#     user: User = Depends(current_user_readonly),
#     db: AsyncSession = Depends(get_db_readonly),
# ):
#     """Get paginated message history with a peer, newest first."""
#     conds = [
#         or_(
#             and_(ChatMessage.sender_id == user.user_id, ChatMessage.receiver_id == peer_id),
#             and_(ChatMessage.sender_id == peer_id, ChatMessage.receiver_id == user.user_id),
#         )
#     ]
#     if before_id:
#         conds.append(ChatMessage.id < before_id)
#     result = await db.execute(
#         select(ChatMessage).where(*conds).order_by(desc(ChatMessage.id)).limit(limit)
#     )
#     messages = result.scalars().all()
#     return {"code": 200, "data": [m.to_dict() | {"user_id": peer_id, 'is_self_sent': m.sender_id == user.user_id} for m in messages]}


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
    # if action == "read_messages":
    #     data = frame.get("data") or {}
    #     peer_id = data.get("peer_id")
    #     if not peer_id:
    #         return {"event": "error", "data": {"msg": "peer_id is required"}}
    #     async with AsyncSessionLocal() as db:
    #         try:
    #             result = await db.execute(
    #                 update(ChatMessage)
    #                 .where(
    #                     ChatMessage.receiver_id == user_id,
    #                     ChatMessage.sender_id == int(peer_id),
    #                     ChatMessage.is_read.is_(False),
    #                 )
    #                 .values(is_read=True)
    #             )
    #             await db.commit()
    #             updated = result.rowcount
    #         except Exception as e:
    #             await db.rollback()
    #             logger.exception("ws read_messages failed")
    #             return {"event": "error", "data": {"msg": str(e)}}
    #     return {"event": "read_ack", "data": {"peer_id": int(peer_id), "updated": updated}}
    # if action == "get_conversations":
    #     async with AsyncSessionLocal() as db:
    #         try:
    #             items = await build_conversations(db, user_id)
    #         except Exception as e:
    #             logger.exception("ws get_conversations failed")
    #             return {"event": "error", "data": {"msg": str(e)}}
    #     return {"event": "conversations", "data": items}
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
    # 启动话术任务(多端连接复用同一个)
    task = _solicit_tasks.get(user_id)
    if task is None or task.done():
        _solicit_tasks[user_id] = asyncio.create_task(solicit_chat_task(user_id))
    try:
        await websocket.send_text(json.dumps({
                    "event": "init",
                    "data": {},
                }, ensure_ascii=False))
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()
            if user and not user.is_review and not user.is_reward_received:
                # 修复竞态：多端同时连 WS 时"先查后改"会重复发奖，改为原子占坑
                claim = await db.execute(
                    update(User)
                    .where(User.user_id == user_id, User.is_reward_received.is_(False))
                    .values(is_reward_received=True)
                )
                if claim.rowcount == 1:
                    user.balance = (user.balance or 0) + 100
                    await add_transaction(user, 100, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_NEW_REWARD, db=db)

                    user.call_card_num = (user.call_card_num or 0) + 3
                    await add_transaction(user, 3, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_NEW_REWARD, db=db)

                    user.match_card_num = (user.match_card_num or 0) + 3
                    await add_transaction(user, 3, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_NEW_REWARD, db=db)

                    user.chat_card_num = (user.chat_card_num or 0) + 5
                    await add_transaction(user, 5, asset_type=ASSET_CHAT_CARD, transaction_type=TRANSACTION_NEW_REWARD, db=db)

                    await send_new_user_welcome_notification(db, user)
                    await db.commit()
                    await db.refresh(user)

                    await send_userinfo_assets_notification(user)
                    await send_new_user_reward_notification(user)

        #     result = await db.execute(
        #         select(ChatMessage)
        #         .where(ChatMessage.receiver_id == user_id, ChatMessage.is_delivered.is_(False))
        #         .order_by(ChatMessage.id.asc())
        #         .limit(500)
        #     )
        #     offline_msgs = result.scalars().all()
        #     if offline_msgs:
        #         await websocket.send_text(json.dumps({
        #             "event": "offline_messages",
        #             "data": [m.to_dict() | {"user_id": m.sender_id if m.sender_id != user_id else m.receiver_id, 'is_self_sent': m.sender_id == user_id} for m in offline_msgs],
        #         }, ensure_ascii=False))
        #         for m in offline_msgs:
        #             m.is_delivered = True
        #         await db.commit()
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
        # 用户所有连接都断开后, 取消话术任务
        if not ws_manager.is_online(user_id) and user_id in _solicit_tasks:
            _solicit_tasks.pop(user_id).cancel()
