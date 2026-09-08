"""
Order database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base
import datetime

class Order(Base):
    """Order model for SQLAlchemy ORM."""
    __tablename__ = "pay_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    package_name = Column(String(100), index=True)
    user_id = Column(Integer, index=True)
    anchor_id = Column(Integer, index=True)
    transaction_no = Column(String, index=True)
    order_no = Column(String, index=True)
    created_time = Column(Integer, index=True)
    updated_time = Column(Integer, index=True)
    sku = Column(String, index=True)
    type = Column(Integer, default=0, index=True)# 0钻石 1首充 2VIP
    order_status = Column(Integer, default=0, index=True)# 0待支付 1支付成功 2支付失败
    currency_code = Column(String, default="USD")
    currency_price = Column(Integer, default=0)
    pp_id = Column(Integer, default=1, index=True) #1 Google
    pp_type = Column(String, default="", index=True)
    path = Column(String, default="", index=True)
    agent = Column(String, default="", index=True)

    def isVip(self):
        return self.type == 2

    def to_dict(self):
        is_failed = self.order_status != 1 and self.created_time < int((datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp())
        if is_failed:
            self.order_status = 2
        return {
            "id": self.id,
            "order_no": self.order_no,
            "transaction_no": self.transaction_no,
            "created_time": self.created_time,
            "updated_time": self.updated_time,
            "sku": self.sku,
            "type": self.type,
            "order_status": self.order_status,
            "currency_code": self.currency_code,
            "currency_price": self.currency_price,
            "pp_type": self.pp_type if len(self.pp_type) > 0 else 'Google',
        }


