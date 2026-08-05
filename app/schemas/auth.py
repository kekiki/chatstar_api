from pydantic import BaseModel

class UserAgent(object):
    """
    User agent object
    """
    def __init__(self, user_agent: str):
        infos = user_agent.split(',')
        # 补齐七段，不足填空字符串
        while len(infos) < 7:
            infos.append("")
        self.app_name, self.app_version, self.build_number, self.deviceModel, self.osVersion, self.brand, self.manufacturer = infos[:7]

class PasswordLoginRequest(BaseModel):
    user_id: int
    password: str

class GoogleAttribution(BaseModel):
    """
    Google attribution request schema
    """
    install_referrer: str
    referrer_click_timestamp_seconds: int
    install_begin_timestamp_seconds: int
    referrer_click_timestamp_server_seconds: int
    install_begin_timestamp_server_seconds: int
    install_version: str
    google_play_instant: bool = False

class GoogleUserInfo(BaseModel):
    """
    Google user info schema
    """
    user_id: str
    nickname: str
    avatar: str
    email: str
    access_token: str

