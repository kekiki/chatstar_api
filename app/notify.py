"""
Notification service: store notification and push it over WebSocket.
"""
import json
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NOTIFY_TYPES, Notification
from app.ws_manager import ws_manager


async def push_notification(
    db: AsyncSession,
    user_id: int,
    notify_type: str,
    title: str,
    content: Optional[Any] = None,
) -> Notification:
    """Create a notification for a user and push it via WebSocket if online."""
    if notify_type not in NOTIFY_TYPES:
        raise ValueError(f"invalid notify_type: {notify_type}")
    notification = Notification(
        user_id=user_id,
        notify_type=notify_type,
        title=title,
        content=json.dumps(content or {}, ensure_ascii=False),
    )
    db.add(notification)
    await db.flush()
    await ws_manager.send_to_user(user_id, "notification", notification.to_dict())
    return notification
