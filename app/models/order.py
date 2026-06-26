"""
Order database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class Order(Base):
    """Order model for SQLAlchemy ORM."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    order_no = Column(String, unique=True, index=True)
    created_at = Column(Integer, unique=True)
    product_id = Column(String, index=True)
    product_type = Column(Integer, default=0)
    order_status = Column(Integer, default=0)
    currency_code = Column(String, default="USD")
    currency_price = Column(Integer, default=0)
    vip_days = Column(Integer, default=0)
    call_card_num = Column(Integer, default=0)
    match_card_num = Column(Integer, default=0)
    chat_card_num = Column(Integer, default=0)

    def to_dict(self):
        return {
            "order_id": self.id,
            "user_id": self.user_id,
            "order_no": self.order_no,
            "created_at": self.created_at,
            "product_id": self.product_id,
            "product_type": self.product_type,
            "order_status": self.order_status,
            "currency_code": self.currency_code,
            "currency_price": self.currency_price,
            "vip_days": self.vip_days,
            "call_card_num": self.call_card_num,
            "match_card_num": self.match_card_num,
            "chat_card_num": self.chat_card_num,
        }
