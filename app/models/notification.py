"""
Notification database model.
"""
from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
import datetime

NOTIFY_TYPES = ("order_status", "gift", "system", "balance")


class Notification(Base):
    __tablename__ = "app_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    notify_type = Column(String(32), index=True)
    title = Column(String(255), default="")
    content = Column(String, default="")
    is_read = Column(Integer, default=0, index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now(), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notify_type": self.notify_type,
            "title": self.title,
            "content": self.content,
            "is_read": self.is_read,
            "created_time": self.created_time,
        }
