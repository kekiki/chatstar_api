"""
Product database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class Product(Base):
    """Product model for SQLAlchemy ORM."""
    __tablename__ = "app_products"
    
    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, index=True)
    sku = Column(String, unique=True)
    diamonds = Column(Integer, default=0)
    reward_diamonds = Column(Integer, default=0)
    discount_type = Column(Integer, default=0)
    currency_code = Column(String, default="USD")
    currency_price = Column(Integer, default=0)
    vip_days = Column(Integer, default=0)
    reward_vip_days = Column(Integer, default=0)
    call_card_num = Column(Integer, default=0)
    match_card_num = Column(Integer, default=0)
    chat_card_num = Column(Integer, default=0)

    def to_dict(self):
        return {
            "sku": self.sku,
            "discount_type": self.discount_type,
            "currency_code": self.currency_code,
            "currency_price": self.currency_price,
            "vip_days": self.vip_days,
            "reward_vip_days": self.reward_vip_days,
            "diamonds": self.diamonds,
            "reward_diamonds": self.reward_diamonds,
            "call_card_num": self.call_card_num,
            "match_card_num": self.match_card_num,
            "chat_card_num": self.chat_card_num,
        }
