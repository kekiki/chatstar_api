"""
Product database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class Product(Base):
    """Product model for SQLAlchemy ORM."""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    productType = Column(Integer, default=0)
    currencyCode = Column(String, default="USD")
    currencyPrice = Column(int, default=0)
    vipDays = Column(Integer, default=0)
    callCardNum = Column(Integer, default=0)
    matchCardNum = Column(Integer, default=0)
    chatCardNum = Column(Integer, default=0)
    discountType=Column(Integer, default=0)

    def toJson(self):
        return {
            "sku": self.sku,
            "productType": self.productType,
            "orderStatus": self.orderStatus,
            "currencyCode": self.currencyCode,
            "currencyPrice": self.currencyPrice,
            "vipDays": self.vipDays,
            "callCardNum": self.callCardNum,
            "matchCardNum": self.matchCardNum,
            "chatCardNum": self.chatCardNum,
            "discountType": self.discountType,
        }
