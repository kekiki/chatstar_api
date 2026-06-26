"""
User database model.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base
import datetime

class User(Base):
    """User model for SQLAlchemy ORM."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    deviceId = Column(String(64), index=True)
    appId = Column(Integer, default=0)
    createdAt = Column(Integer, default=lambda: int(datetime.datetime.now().timestamp()))
    country = Column(String(64), default="US")
    nickname = Column(String(64))
    avatar = Column(String)
    email = Column(String(128), index=True)
    googleId = Column(String(128), index=True)
    balance = Column(Integer, default=0)
    isAnchor = Column(Boolean, default=False)
    isVip = Column(Boolean, default=False)
    vipExpireTime = Column(DateTime)
    languageName = Column(String(64), default="English")
    languageCode = Column(String(16), default="en")
    followCount = Column(Integer, default=0)
    fansCount = Column(Integer, default=0)
    likeCount = Column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "deviceId": self.deviceId,
            "country": self.country,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "email": self.email,
            "balance": self.balance,
            "isVip": self.isVip,
            "vipExpireTime": self.vipExpireTime.isoformat() if self.vipExpireTime else None,
            "languageName": self.languageName,
            "languageCode": self.languageCode,
            "followCount": self.followCount,
            "fansCount": self.fansCount,
            "likeCount": self.likeCount,
        }
