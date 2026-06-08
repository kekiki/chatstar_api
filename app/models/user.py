"""
User database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class User(Base):
    """User model for SQLAlchemy ORM."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    hashed_password = Column(String)
    device_id = Column(String, unique=True, index=True)
