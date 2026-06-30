from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base
import datetime

class Anchor(Base):
    __tablename__ = "app_anchors"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())
    country = Column(String(64), default="US")
    nickname = Column(String(100))
    avatar = Column(String)
    age = Column(Integer, default=20)
    language_name = Column(String(64), default="English")
    language_code = Column(String(16), default="en")
    follow_count = Column(Integer, default=0)
    fans_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    is_check = Column(Boolean, default=False)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_time": self.created_time,
            "country": self.country,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "age": self.age,
            "language_name": self.language_name,
            "language_code": self.language_code,
            "follow_count": self.follow_count,
            "fans_count": self.fans_count,
            "like_count": self.like_count,
            "is_check": self.is_check,
        }
