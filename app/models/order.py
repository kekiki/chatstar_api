"""
Order database model.
"""
from sqlalchemy import Column, Integer, String, ForeignKey
from app.database import Base


class Order(Base):
    """Order model for SQLAlchemy ORM."""
    __tablename__ = "pay_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("app_list.id"), index=True)
    user_id = Column(Integer, index=True)
    order_no = Column(String, index=True)
    created_time = Column(Integer)
    sku = Column(String)
    discount_type = Column(Integer, default=0)# 0普通折扣 1首充折扣
    order_status = Column(Integer, default=0)# 0待支付 1支付成功 2支付失败
    currency_code = Column(String, default="USD")
    currency_price = Column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "order_no": self.order_no,
            "created_time": self.created_time,
            "sku": self.sku,
            "discount_type": self.discount_type,
            "order_status": self.order_status,
            "currency_code": self.currency_code,
            "currency_price": self.currency_price,
        }
