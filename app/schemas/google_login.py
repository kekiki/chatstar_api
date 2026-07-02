from pydantic import BaseModel

class GoogleLogin(BaseModel):
    """
    Google login request schema
    """
    user_id: str
    nickname: str
    avatar: str
    email: str
    access_token: str