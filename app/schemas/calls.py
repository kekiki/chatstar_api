from typing import Optional

from pydantic import BaseModel

class CreateCallRequest(BaseModel):
    call_type: int
    peer_id: Optional[int] = None        # int 通话类型

class RenewCallRequest(BaseModel):
    call_id: int # int 通话ID

class HangupCallRequest(BaseModel):
    call_id: int # int 通话ID