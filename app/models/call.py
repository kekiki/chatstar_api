"""
Call database model.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base
import datetime


class Call(Base):
    """Media model for SQLAlchemy ORM."""
    __tablename__ = "app_calls"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    anchor_id = Column(Integer, index=True)
    url = Column(String, default="")
    call_type = Column(Integer, index=True, default=0) # 0: Call, 1: AIV, 2: AIB, 3: Match
    call_duration = Column(Integer, default=0)
    is_ended = Column(Boolean, default=False)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())
    updated_time = Column(DateTime, default=lambda: datetime.datetime.now(), onupdate=lambda: datetime.datetime.now())

    def to_dict(self):
        
        return {
            "id": self.id,
            "peer_id": self.anchor_id,
            "url": self.url,
            "call_type": self.call_type,
        }
