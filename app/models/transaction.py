"""
Transaction database model.
"""
from sqlalchemy import Column, Integer, DateTime
from app.database import Base
import datetime

# 资产分类
ASSET_DIAMOND = 0     # 钻石交易
ASSET_VIP = 1         # VIP交易
ASSET_CALL_CARD = 2   # 通话卡交易
ASSET_MATCH_CARD = 3  # 匹配卡交易
ASSET_CHAT_CARD = 4   # 聊天卡交易

# 交易类型
TRANSACTION_PURCHASE = 0  # 购买
TRANSACTION_GIFT = 1  # 送礼
TRANSACTION_CHAT = 2  # 聊天
TRANSACTION_TASK = 3  # 任务奖励

class Transaction(Base):
    """Transaction model for SQLAlchemy ORM."""
    __tablename__ = "app_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    amount = Column(Integer)
    asset_type = Column(Integer, default=ASSET_DIAMOND, index=True)  # 资产类型: 钻石、VIP、通话卡、匹配卡、聊天卡
    transaction_type = Column(Integer, default=TRANSACTION_PURCHASE, index=True)
    created_time = Column(DateTime, default=lambda: datetime.datetime.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "asset_type": self.asset_type,
            "transaction_type": self.transaction_type,
            "created_time": self.created_time,
        }
