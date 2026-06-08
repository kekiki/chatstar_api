"""
User database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class User(Base):
    """User model for SQLAlchemy ORM."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    hashed_password = Column(String)
    device_id = Column(String, unique=True, index=True)
    created_at = Column(Integer, unique=True)
    country = Column(String, default="US")
    nickname = Column(String)
    avatar = Column(String)
    balance = Column(Integer, default=0)
    is_vip = Column(bool, default=False)
    vipEndTime = Column(Integer, default=0)
    language = Column(String, default="en")
    isDisturb = Column(bool, default=False)

    def toJson(self):
        return {
            "user_id": self.id,
            "device_id": self.device_id,
            "created_at": self.created_at,
            "country": self.country,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "balance": self.balance,
            "is_vip": self.is_vip,
            "vipEndTime": self.vipEndTime,
            "language": self.language,
            "isDisturb": self.isDisturb
        }
