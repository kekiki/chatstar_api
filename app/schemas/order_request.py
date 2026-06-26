from pydantic import BaseModel
from typing import Optional


class CreateOrderRequest(BaseModel):
    user_id: int
    order_no: Optional[str] = None
    product_id: str
    product_type: int = 0
    currency_code: str = "USD"
    currency_price: int = 0
    vip_days: int = 0
    call_card_num: int = 0
    match_card_num: int = 0
    chat_card_num: int = 0


class VerifyGoogleRequest(BaseModel):
    order_no: str
    purchase_token: str
    product_id: str
    package_name: str
