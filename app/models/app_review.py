from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
import datetime

class AppReview(Base):
    __tablename__ = "app_review"
    id = Column(Integer, primary_key=True)
    package_name = Column(String(100), index=True)
    app_version = Column(String(16), index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())