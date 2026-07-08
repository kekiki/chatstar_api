"""
Media database model.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base
import datetime


class Media(Base):
    """Media model for SQLAlchemy ORM."""
    __tablename__ = "app_medias"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    cover = Column(String, default="")
    url = Column(String, default="")
    is_vip = Column(Boolean, default=False)
    is_video = Column(Boolean, default=False)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "cover": self.cover,
            "url": self.url,
            "is_vip": self.is_vip,
            "is_video": self.is_video,
        }
