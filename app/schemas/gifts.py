from pydantic import BaseModel, Field


class SendGiftRequest(BaseModel):
    gift_id: int = Field(..., description="礼物ID")
    receiver_id: int = Field(..., description="接收者用户ID")
    quantity: int = Field(default=1, ge=1, le=100, description="赠送数量")
