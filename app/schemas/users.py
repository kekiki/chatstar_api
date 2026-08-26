from pydantic import BaseModel
from typing import Optional

class DeleteAccountWithAccountPasswordRequest(BaseModel):
    user_id: int
    password: str

class SetPasswordRequest(BaseModel):
    password: str

class UpdateFirebaseTokenRequest(BaseModel):
    firebase_token: str

class GoogleTranslateRequest(BaseModel):
    """
    Google translate request schema
    """
    text: str
    target_language: str

class UpdateUserInfoRequest(BaseModel):
    avatar: Optional[str] = None        # 头像
    nickname: Optional[str] = None      # 昵称
    birthday: Optional[int] = None      # 生日（Unix时间戳）