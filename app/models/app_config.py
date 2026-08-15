from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
import datetime

class AppConfig(Base):
    __tablename__ = "app_config"
    id = Column(Integer, primary_key=True)
    package_name = Column(String(100), unique=True, index=True)
    app_version = Column(String(16), index=True)
    key = Column(String(64), index=True)
    value = Column(String)
    remark = Column(String)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())