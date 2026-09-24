from typing import Literal, Optional

from pydantic import BaseModel

class CreateCallRequest(BaseModel):
    call_type: int
    peer_id: Optional[int] = None        # int 通话类型