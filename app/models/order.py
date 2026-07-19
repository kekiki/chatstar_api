"""
Order database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


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
    discount_type = Column(Integer, default=0, index=True)# 0普通折扣 1首充折扣
    order_status = Column(Integer, default=0, index=True)# 0待支付 1支付成功 2支付失败
    currency_code = Column(String, default="USD")
    currency_price = Column(Integer, default=0)
    pp_id = Column(Integer, default=1, index=True) #1 Google
    pp_type = Column(String, default="", index=True)
    path = Column(String, default="", index=True)
    agent = Column(String, default="", index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "transaction_no": self.transaction_no,
            "created_time": self.created_time,
            "sku": self.sku,
            "discount_type": self.discount_type,
            "order_status": self.order_status,
            "currency_code": self.currency_code,
            "currency_price": self.currency_price,
        }
