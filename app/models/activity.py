from sqlalchemy import Column, Date, Integer

from app.database import Base


class DailyUserActivity(Base):
    __tablename__ = "daily_user_activity"

    stat_date = Column(Date, primary_key=True)
    user_id = Column(Integer, primary_key=True)
