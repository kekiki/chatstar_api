from pydantic import BaseModel
from typing import Optional


class CreateOrderRequest(BaseModel):
    user_id: int
    order_no: Optional[str] = None
    sku: str
    discount_type: int = 0
    currency_code: str = "USD"
    currency_price: int = 0


class VerifyGoogleRequest(BaseModel):
    order_no: str
    purchase_token: str
    product_id: str
    package_name: str
