from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base

class AppReview(Base):
    __tablename__ = "app_review"
    id = Column(Integer, primary_key=True)
    package_name = Column(String(100), index=True)
    app_version = Column(String(16), index=True)