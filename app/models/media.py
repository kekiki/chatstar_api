"""
Media database model.
"""
from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class Media(Base):
    """Media model for SQLAlchemy ORM."""
    __tablename__ = "medias"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    url = Column(String, default="")
    is_vip = Column(Boolean, default=False)
    is_video = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "url": self.url,
            "is_vip": self.is_vip,
            "is_video": self.is_video,
        }
