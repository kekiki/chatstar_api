from pydantic import BaseModel, ConfigDict, Field

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
    model_config = ConfigDict(populate_by_name=True)

    install_referrer: str = Field(alias="installReferrer")
    referrer_click_timestamp_seconds: int = Field(alias="referrerClickTimestampSeconds")
    install_begin_timestamp_seconds: int = Field(alias="installBeginTimestampSeconds")
    referrer_click_timestamp_server_seconds: int = Field(alias="referrerClickTimestampServerSeconds")
    install_begin_timestamp_server_seconds: int = Field(alias="installBeginTimestampServerSeconds")
    install_version: str = Field(alias="installVersion")
    google_play_instant: bool = Field(default=False, alias="googlePlayInstant")

class GoogleUserInfo(BaseModel):
    """
    Google user info schema
    """
    user_id: str
    nickname: str
    avatar: str
    email: str
    access_token: str

