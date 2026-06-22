"""
Anchor database model.
"""
from sqlalchemy import Column, Integer, String, Boolean
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
    followcount = Column(Integer, default=0)
    fanscount = Column(Integer, default=0)
    likecount = Column(Integer, default=0)

    def toJson(self):
        return {
            "anchorId": self.id,
            "createdAt": self.createdAt,
            "country": self.country,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "language": self.language,
            "followCount": self.followcount,
            "fansCount": self.fanscount,
            "likeCount": self.likecount,
        }
