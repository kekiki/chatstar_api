"""
Chat message database model.
"""
import datetime
import json

from sqlalchemy import Boolean, Column, Integer, String, Text

from app.database import Base

MSG_TYPES = ("text", "image", "video", "gift")


class ChatMessage(Base):
    """One-to-one chat message between user and anchor."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    msg_no = Column(String(64), unique=True, index=True)
    sender_id = Column(Integer, index=True)
    receiver_id = Column(Integer, index=True)
    msg_type = Column(String(16), default="text", index=True)  # text/image/video/gift
    content = Column(Text, default="")  # text 为纯文本, 其余类型为 JSON 字符串
    is_delivered = Column(Boolean, default=False, index=True)
    is_read = Column(Boolean, default=False, index=True)
    created_time = Column(Integer, default=lambda: int(datetime.datetime.now().timestamp()), index=True)

    def content_data(self):
        if self.msg_type == "text":
            return self.content
        try:
            return json.loads(self.content)
        except (TypeError, ValueError):
            return self.content

    def to_dict(self):
        return {
            "id": self.msg_no,
            "type": self.msg_type,
            "content": self.content_data(),
            "timestamp": self.created_time,
        }
