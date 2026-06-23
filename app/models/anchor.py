"""
Anchor database model.
"""
from sqlalchemy import Column, Integer, String, Boolean, ARRAY
from app.database import Base


class Anchor(Base):
    """Anchor model for SQLAlchemy ORM."""
    __tablename__ = "anchors"
    
    id = Column(Integer, primary_key=True, index=True)
    createdAt = Column(Integer, unique=True)
    country = Column(String, default="US")
    nickname = Column(String)
    avatar = Column(String)
    language = Column(String, default="en")
    followCount = Column(Integer, default=0)
    fansCount = Column(Integer, default=0)
    likeCount = Column(Integer, default=0)

    def toJson(self):
        return {
            "anchorId": self.id,
            "createdAt": self.createdAt,
            "country": self.country,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "language": self.language,
            "followCount": self.followCount,
            "fansCount": self.fansCount,
            "likeCount": self.likeCount,
        }
