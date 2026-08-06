"""
Notification database model.
"""
import datetime
import json

from sqlalchemy import Boolean, Column, Integer, String, Text

from app.database import Base

NOTIFY_TYPES = ("balance_change", "order_status", "gift_pack", "system")


class Notification(Base):
    """User notification pushed over WebSocket and stored for offline query."""
    __tablename__ = "app_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    notify_type = Column(String(32), default="system", index=True)  # balance_change/order_status/gift_pack/system
    title = Column(String(255), default="")
    content = Column(Text, default="")  # JSON 字符串
    is_read = Column(Boolean, default=False, index=True)
    created_time = Column(Integer, default=lambda: int(datetime.datetime.now().timestamp()), index=True)

    def content_data(self):
        try:
            return json.loads(self.content)
        except (TypeError, ValueError):
            return self.content

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notify_type": self.notify_type,
            "title": self.title,
            "content": self.content_data(),
            "is_read": self.is_read,
            "created_time": self.created_time,
        }
