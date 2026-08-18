"""
Block database model.
"""
from sqlalchemy import Column, Integer, DateTime
from app.database import Base
import datetime


class UserBlock(Base):
    """Block model for SQLAlchemy ORM."""
    __tablename__ = "app_user_blocks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    block_user_id = Column(Integer, index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "block_user_id": self.block_user_id,
        }
