from typing import Literal, Optional

from pydantic import BaseModel

class SendMessageRequest(BaseModel):
    receiver_id: int
    msg_type: Literal["text", "image", "video", "gift"] = "text"
    content: Optional[str] = None        # text 消息文本
    media_url: Optional[str] = None      # image/video 资源地址
    media_cover: Optional[str] = None    # video 封面
    gift_id: Optional[int] = None        # gift 消息礼物ID
    gift_count: int = 1