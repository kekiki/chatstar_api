from pydantic import BaseModel

class DeleteAccountWithAccountPasswordRequest(BaseModel):
    user_id: int
    password: str

class SetPasswordRequest(BaseModel):
    password: str

class UpdateFirebaseTokenRequest(BaseModel):
    firebase_token: str

class UserInfoRequest(BaseModel):
    user_id: int

class GoogleTranslateRequest(BaseModel):
    """
    Google translate request schema
    """
    text: str
    target_language: str