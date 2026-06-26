from sqlalchemy import Column, Integer, String, Boolean
from database import Base

class AppList(Base):
    __tablename__ = "app_list"
    id = Column(Integer, primary_key=True)
    app_name = Column(String(100))
    package_name = Column(String(100))
    is_online = Column(Boolean, default=True)