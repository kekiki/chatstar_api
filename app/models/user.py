"""
User database model.
"""
from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base
import datetime

class User(Base):
    """User model for SQLAlchemy ORM."""
    __tablename__ = "app_users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    device_id = Column(String(100), index=True)
    app_id = Column(Integer, default=0)
    created_time = Column(Integer, default=lambda: int(datetime.datetime.now().timestamp()))
    country = Column(String(64), default="US")
    ip = Column(String(64))
    nickname = Column(String(64))
    avatar = Column(String)
    email = Column(String(128), index=True)
    google_id = Column(String(128), index=True)
    balance = Column(Integer, default=0)
    is_vip = Column(Boolean, default=False)
    vip_expire_time = Column(Integer)
    language_name = Column(String(64), default="English")
    language_code = Column(String(16), default="en")
    follow_count = Column(Integer, default=0)
    fans_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    is_check = Column(Boolean, default=False)
    agent = Column(String(255))
    # Install referrer tracking
    install_referrer = Column(String(255))
    referrer_click_timestamp_seconds = Column(Integer)
    install_begin_timestamp_seconds = Column(Integer)
    referrer_click_timestamp_server_seconds = Column(Integer)
    install_begin_timestamp_server_seconds = Column(Integer)
    install_version = Column(String(64))
    google_play_instant = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "country": self.country,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "email": self.email,
            "balance": self.balance,
            "is_vip": self.is_vip,
            "vip_expire_time": self.vip_expire_time,
            "language_name": self.language_name,
            "language_code": self.language_code,
            "follow_count": self.follow_count,
            "fans_count": self.fans_count,
            "like_count": self.like_count,
            "r_flag": self.is_check,
        }
