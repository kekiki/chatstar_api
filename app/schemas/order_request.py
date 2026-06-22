from pydantic import BaseModel
from typing import Optional


class CreateOrderRequest(BaseModel):
    userId: int
    orderNo: Optional[str] = None
    productId: str
    productType: int = 0
    currencyCode: str = "USD"
    currencyPrice: int = 0
    vipDays: int = 0
    callCardNum: int = 0
    matchCardNum: int = 0
    chatCardNum: int = 0


class VerifyGoogleRequest(BaseModel):
    orderNo: str
    purchaseToken: str
    productId: str
    packageName: str
