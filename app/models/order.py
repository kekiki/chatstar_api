"""
Order database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base
import datetime

# 订单状态
ORDER_STATUS_PENDING = 0    # 待支付
ORDER_STATUS_PAID = 1       # 支付成功
ORDER_STATUS_FAILED = 2     # 支付失败/取消
ORDER_STATUS_REFUNDED = 3   # 已退款（Google 退款/撤销）

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
    order_status = Column(Integer, default=0, index=True)# 0待支付 1支付成功 2支付失败 3已退款
    currency_code = Column(String, default="USD")
    currency_price = Column(Integer, default=0)
    pp_id = Column(Integer, default=1, index=True) #1 Google
    pp_type = Column(String, default="", index=True)
    path = Column(String, default="", index=True)
    agent = Column(String, default="", index=True)
    # Google Play 购买凭据，唯一索引防止同一笔购买在多个订单上重放
    purchase_token = Column(String, unique=True, index=True)
    google_order_id = Column(String, index=True)
    # 实际到账的购买及赠送钻石总数；NULL 表示上线前的旧订单。
    google_granted_diamonds = Column(Integer, nullable=True)

    def isVip(self):
        return self.type == 2

    def to_dict(self):
        status = self.order_status
        if status == ORDER_STATUS_PENDING and self.created_time < int((datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp()):
            status = ORDER_STATUS_FAILED
        return {
            "id": self.id,
            "order_no": self.google_order_id if self.google_order_id else self.order_no,
            "transaction_no": self.transaction_no,
            "created_time": self.created_time,
            "updated_time": self.updated_time,
            "sku": self.sku,
            "type": self.type,
            "order_status": status,
            "currency_code": self.currency_code,
            "currency_price": self.currency_price,
            "pp_type": self.pp_type if len(self.pp_type) > 0 else 'Google',
        }


