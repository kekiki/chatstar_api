"""
Report database model.
"""
from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
import datetime


class UserReport(Base):
    """Report model for SQLAlchemy ORM."""
    __tablename__ = "app_user_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    report_user_id = Column(Integer, index=True)
    reason = Column(String(255), default="")
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "report_user_id": self.report_user_id,
            "reason": self.reason,
        }
