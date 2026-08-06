from typing import List, Literal, Optional

from pydantic import BaseModel


class SendMessageRequest(BaseModel):
    receiver_id: int
    msg_type: Literal["text", "image", "video", "gift"] = "text"
    content: Optional[str] = None        # text 消息文本
    media_url: Optional[str] = None      # image/video 资源地址
    media_cover: Optional[str] = None    # video 封面
    media_width: Optional[int] = None
    media_height: Optional[int] = None
    media_duration: Optional[int] = None  # video 时长(秒)
    gift_id: Optional[int] = None        # gift 消息礼物ID
    gift_count: int = 1


class ReadMessagesRequest(BaseModel):
    peer_id: int


class NotifyReadRequest(BaseModel):
    ids: Optional[List[int]] = None  # None 或空列表表示全部已读
