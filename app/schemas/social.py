"""Request schemas for social routes."""
from typing import Optional

from pydantic import BaseModel, Field


class TargetUserRequest(BaseModel):
    target_user_id: Optional[int] = Field(default=None, description="目标用户ID")


class ReportUserRequest(BaseModel):
    target_user_id: Optional[int] = Field(default=None, description="被举报用户ID")
    reason: str = Field(default="", max_length=255, description="举报原因")
