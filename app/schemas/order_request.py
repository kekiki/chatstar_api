from pydantic import BaseModel
from typing import Optional


class CreateOrderRequest(BaseModel):
    sku: str
    type: int
    path: Optional[str] = None
    pp_id: Optional[int] = 1
    anchor_id: Optional[int] = None

class VerifyGoogleRequest(BaseModel):
    order_no: str
    purchase_token: str
    product_id: str
    package_name: str
