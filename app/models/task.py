from sqlalchemy import Column, Integer, String, DateTime, Date, UniqueConstraint
from app.database import Base
import datetime

# 任务分类
CATEGORY_SIGNIN = 0   # 签到任务
CATEGORY_DAILY = 1    # 每日任务
CATEGORY_NEWCOMER = 2 # 新手任务

# 任务记录状态
STATUS_DOING = 0    # 进行中
STATUS_CLAIMABLE = 1 # 已完成待领取
STATUS_CLAIMED = 2  # 已领取

#任务类型
TYPE_FOLLOW_USERS = "follow_users" # 关注
TYPE_UNLOCK_VIP = "unlock_vip" # 解锁VIP
TYPE_FIRST_RECHARGE = "first_recharge" # 首充
TYPE_ACTIVE_CALL = "active_call" # 主动通话
TYPE_RATE_APP = "rate_app" # 评分应用
TYPE_SEND_GIFT = "send_gift" # 送礼
TYPE_MATCH_TIMES = "match_times" # 匹配次数
TYPE_RECHARGE_TIMES = "recharge_times" # 充值次数

class Task(Base):
    __tablename__ = "app_tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    desc = Column(String(255))
    icon = Column(String(255))
    num = Column(Integer, default=0) # 签到任务:第几天(1-7); 其他任务:需要完成的次数
    category = Column(Integer, default=0, index=True) # 0:签到任务，1:每日任务，2:新手任务
    type = Column(String(50), default="", index=True) # 事件类型: 关注、解锁VIP、首充等
    reward_diamonds = Column(Integer, default=0)
    call_card_num = Column(Integer, default=0)
    match_card_num = Column(Integer, default=0)
    chat_card_num = Column(Integer, default=0)
    sort = Column(Integer, default=0)
    status = Column(Integer, default=1) # 0:下架 1:上架

    def to_dict(self):
        return {
            "id": self.id,
            "icon": self.icon,
            "num": self.num,
            "category": self.category,
            "type": self.type,
            "reward_diamonds": self.reward_diamonds,
            "call_card_num": self.call_card_num,
            "match_card_num": self.match_card_num,
            "chat_card_num": self.chat_card_num,
            "sort": self.sort,
        }

class TaskRecord(Base):
    __tablename__ = "app_task_records"
    __table_args__ = (
        UniqueConstraint("user_id", "task_id", "task_date", name="uq_task_record_user_task_date"),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    task_id = Column(Integer, index=True)
    category = Column(Integer, default=0, index=True) # 0:签到任务，1:每日任务，2:新手任务
    progress = Column(Integer, default=0) # 签到任务:连续签到第几天; 其他任务:已完成次数
    status = Column(Integer, default=0) # 0:进行中 1:已完成待领取 2:已领取(签到即领取)
    task_date = Column(Date, index=True) # 每日任务:所属日期; 签到任务:签到日期; 新手任务:NULL
    created_time = Column(DateTime, default=lambda: datetime.datetime.now(), index=True)
    updated_time = Column(DateTime, default=lambda: datetime.datetime.now(), onupdate=lambda: datetime.datetime.now())
