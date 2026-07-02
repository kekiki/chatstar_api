from pydantic import BaseModel

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