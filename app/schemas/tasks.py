"""
Task request schemas.
"""
from pydantic import BaseModel, Field


class TaskReportRequest(BaseModel):
    type: str = Field(..., description="事件类型, 如 recharge/follow")
    num: int = Field(default=1, ge=1, description="完成的次数增量")


class TaskReceiveRequest(BaseModel):
    task_id: int = Field(..., description="任务ID")
