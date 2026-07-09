"""
Like database model.
"""
from sqlalchemy import Column, Integer, DateTime
from app.database import Base
import datetime


class UserLike(Base):
    """Like model for SQLAlchemy ORM."""
    __tablename__ = "app_user_likes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    like_user_id = Column(Integer, index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "like_user_id": self.like_user_id,
        }
