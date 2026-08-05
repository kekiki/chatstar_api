from sqlalchemy import Column, Integer, String
from app.database import Base

class Task(Base):
    __tablename__ = "app_tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    desc = Column(String(255))
    icon = Column(String(255))
    num = Column(Integer, default=0) # 签到任务的第几天, 其他任务需要完成的次数
    category = Column(Integer, default=0, index=True) # 0:签到任务，1:每日任务，2:新手任务
    type = Column(String(50), default="", index=True)
    diamonds = Column(Integer)
    call_card_num = Column(Integer, default=0)
    match_card_num = Column(Integer, default=0)
    chat_card_num = Column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "desc": self.desc,
            "icon": self.icon,
            "num": self.num,
            "category": self.category,
            "type": self.type,
            "diamonds": self.diamonds,
            "call_card_num": self.call_card_num,
            "match_card_num": self.match_card_num,
            "chat_card_num": self.chat_card_num,
        }