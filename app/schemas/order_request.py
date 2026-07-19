from pydantic import BaseModel
from typing import Optional


class CreateOrderRequest(BaseModel):
    sku: str
    path: Optional[str] = None

class VerifyGoogleRequest(BaseModel):
    order_no: str
    purchase_token: str
    product_id: str
    package_name: str
