"""
Order database model.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class Order(Base):
    """Order model for SQLAlchemy ORM."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    orderNo = Column(String, unique=True, index=True)
    createdAt = Column(Integer, unique=True)
    productId = Column(String, unique=True, index=True)
    productType = Column(Integer, default=0)
    orderStatus = Column(Integer, default=0)
    currencyCode = Column(String, default="USD")
    currencyPrice = Column(int, default=0)
    vipDays = Column(Integer, default=0)
    callCardNum = Column(Integer, default=0)
    matchCardNum = Column(Integer, default=0)
    chatCardNum = Column(Integer, default=0)

    def toJson(self):
        return {
            "orderId": self.id,
            "orderNo": self.orderNo,
            "createdAt": self.createdAt,
            "productId": self.productId,
            "productType": self.productType,
            "orderStatus": self.orderStatus,
            "currencyCode": self.currencyCode,
            "currencyPrice": self.currencyPrice,
            "vipDays": self.vipDays,
            "callCardNum": self.callCardNum,
            "matchCardNum": self.matchCardNum,
            "chatCardNum": self.chatCardNum,
        }
