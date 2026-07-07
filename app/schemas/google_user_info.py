from pydantic import BaseModel

class GoogleUserInfo(BaseModel):
    """
    Google user info schema
    """
    user_id: str
    nickname: str
    avatar: str
    email: str
    access_token: str