from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class CreateOrderRequest(BaseModel):
    sku: str
    type: int
    path: Optional[str] = None
    pp_id: Optional[int] = 1
    anchor_id: Optional[int] = None

class VerifyGoogleRequest(BaseModel):
    """Client payload used to verify a Google Play purchase.

    The mobile client sends camelCase JSON.  ``transaction_no`` is the
    obfuscated profile ID supplied to Google Billing when the order starts;
    it lets the server recover the app order even when the purchase callback
    happens later or after the app restarts.
    """

    model_config = ConfigDict(populate_by_name=True)

    order_no: Optional[str] = Field(default=None, alias="orderNo")
    transaction_no: Optional[str] = Field(default=None, alias="transactionNo")
    purchase_token: str = Field(alias="purchaseToken")
    product_id: Optional[str] = Field(default=None, alias="productId")
    package_name: Optional[str] = Field(default=None, alias="packageName")
    google_order_id: Optional[str] = Field(default=None, alias="orderId")
    json_purchase_info: Optional[str] = Field(default=None, alias="jsonPurchaseInfo")
