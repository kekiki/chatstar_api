from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
import datetime

class Gift(Base):
    __tablename__ = "app_gifts"
    id = Column(Integer, primary_key=True)
    gift_name = Column(String(100))
    gift_icon = Column(String(255))
    gift_price = Column(Integer)
    gift_animation = Column(String(255))

    def to_dict(self):
        return {
            "id": self.id,
            "gift_name": self.gift_name,
            "gift_icon": self.gift_icon,
            "gift_price": self.gift_price,
            "gift_animation": self.gift_animation,
        }

class GiftRecord(Base):
    __tablename__ = "app_gift_records"
    id = Column(Integer, primary_key=True)
    gift_id = Column(Integer, index=True)
    gift_name = Column(String(100))
    gift_icon = Column(String(255))
    gift_price = Column(Integer)
    sender_id = Column(Integer, index=True)
    sender_name = Column(String(100))
    sender_avatar = Column(String(255))
    receiver_id = Column(Integer, index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now(), index=True)

    def to_dict(self):
        return {
            "gift_id": self.gift_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "sender_avatar": self.sender_avatar,
            "receiver_id": self.receiver_id,
            "gift_name": self.gift_name,
            "gift_icon": self.gift_icon,
            "gift_price": self.gift_price,
        }