# Schemas package
# This package contains Pydantic models for request/response validation

from .auth import GoogleUserInfo, GoogleAttribution, UserAgent, PasswordLoginRequest
from .orders import CreateOrderRequest, VerifyGoogleRequest
from .users import GoogleTranslateRequest, DeleteAccountWithAccountPasswordRequest, SetPasswordRequest, UpdateFirebaseTokenRequest, UpdateUserInfoRequest
from .tasks import TaskReportRequest, TaskReceiveRequest
from .chat import SendMessageRequest
from .gifts import SendGiftRequest
from .social import TargetUserRequest, ReportUserRequest

__all__ = [
    "GoogleUserInfo",
    "GoogleAttribution",
    "CreateOrderRequest",
    "VerifyGoogleRequest",
    "UserAgent",
    "GoogleTranslateRequest",
    "DeleteAccountWithAccountPasswordRequest",
    "SetPasswordRequest",
    "UpdateFirebaseTokenRequest",
    "UpdateUserInfoRequest",
    "PasswordLoginRequest",
    "TaskReportRequest",
    "TaskReceiveRequest",
    "SendMessageRequest",
    "SendGiftRequest",
    "TargetUserRequest",
    "ReportUserRequest",
]
