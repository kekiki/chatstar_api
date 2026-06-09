"""
User database model.
"""
from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class User(Base):
    """User model for SQLAlchemy ORM."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    deviceId = Column(String, unique=True, index=True)
    createdAt = Column(Integer, unique=True)
    country = Column(String, default="US")
    nickname = Column(String)
    avatar = Column(String)
    balance = Column(Integer, default=0)
    isVip = Column(Boolean, default=False)
    vipEndTime = Column(Integer, default=0)
    language = Column(String, default="en")
    isDisturb = Column(Boolean, default=False)

    def toJson(self):
        return {
            "userId": self.id,
            "deviceId": self.deviceId,
            "createdAt": self.createdAt,
            "country": self.country,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "balance": self.balance,
            "isVip": self.isVip,
            "vipEndTime": self.vipEndTime,
            "language": self.language,
            "isDisturb": self.isDisturb
        }
