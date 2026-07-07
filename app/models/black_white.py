"""
BlackWhite database model.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base
import datetime


class BlackWhiteUser(Base):
    """BlackWhiteUser model for SQLAlchemy ORM."""
    __tablename__ = "app_black_white_user"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    status = Column(Integer, default=0, index=True)  # 0: review, 1: black, 2: white
    remarks = Column(String, default="", index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())

class BlackWhiteIp(Base):
    """BlackWhiteIp model for SQLAlchemy ORM."""
    __tablename__ = "app_black_white_ip"
    
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, index=True)
    status = Column(Integer, default=0, index=True)  # 0: review, 1: black, 2: white
    remarks = Column(String, default="", index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())

class BlackWhiteDevice(Base):
    """BlackWhiteDevice model for SQLAlchemy ORM."""
    __tablename__ = "app_black_white_device"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    status = Column(Integer, default=0, index=True)  # 0: review, 1: black, 2: white
    remarks = Column(String, default="", index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())