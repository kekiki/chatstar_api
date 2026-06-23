"""
Media database model.
"""
from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class Media(Base):
    """Media model for SQLAlchemy ORM."""
    __tablename__ = "medias"
    
    id = Column(Integer, primary_key=True, index=True)
    userId = Column(String, index=True)
    url = Column(String, default="")
    isVip = Column(Boolean, default=False)
    isVideo = Column(Boolean, default=False)

    def toJson(self):
        return {
            "userId": self.userId,
            "url": self.url,
            "isVip": self.isVip,
            "isVideo": self.isVideo,
        }
