"""
Task routes: task list with progress, signin, progress report, reward claim.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_readonly
from app.models import Task, TaskRecord, User
from app.models.task import (
    CATEGORY_SIGNIN, CATEGORY_DAILY, CATEGORY_NEWCOMER,
    STATUS_DOING, STATUS_CLAIMABLE, STATUS_CLAIMED,
)
from app.schemas import TaskReportRequest, TaskReceiveRequest
from app.security import current_user

router = APIRouter(prefix="/api", tags=["tasks"])

SIGNIN_CYCLE_DAYS = 7


def _reward_dict(task: Task) -> dict:
    return {
        "reward_diamonds": task.reward_diamonds or 0,
        "call_card_num": task.call_card_num or 0,
        "match_card_num": task.match_card_num or 0,
        "chat_card_num": task.chat_card_num or 0,
    }


def _grant_reward(user: User, task: Task) -> None:
    user.balance = (user.balance or 0) + (task.reward_diamonds or 0)
    user.call_card_num = (user.call_card_num or 0) + (task.call_card_num or 0)
    user.match_card_num = (user.match_card_num or 0) + (task.match_card_num or 0)
    user.chat_card_num = (user.chat_card_num or 0) + (task.chat_card_num or 0)


async def _get_record(db: AsyncSession, user_id: int, task: Task, today: datetime.date) -> TaskRecord | None:
    query = select(TaskRecord).where(TaskRecord.user_id == user_id, TaskRecord.task_id == task.id)
    if task.category == CATEGORY_DAILY:
        query = query.where(TaskRecord.task_date == today)
    else:
        query = query.where(TaskRecord.task_date.is_(None))
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def add_task_progress(db: AsyncSession, user_id: int, event_type: str, num: int = 1) -> list:
    """Increment progress for daily/newcomer tasks matching the event type.

    Returns the list of updated records. Signin tasks are not affected.
    """
    today = datetime.date.today()
    result = await db.execute(
        select(Task).where(
            Task.type == event_type,
            Task.category.in_([CATEGORY_DAILY, CATEGORY_NEWCOMER]),
            Task.status == 1,
        )
    )
    tasks = result.scalars().all()
    updated = []
    for task in tasks:
        record = await _get_record(db, user_id, task, today)
        if record is None:
            record = TaskRecord(
                user_id=user_id,
                task_id=task.id,
                category=task.category,
                progress=0,
                status=STATUS_DOING,
                task_date=today if task.category == CATEGORY_DAILY else None,
            )
            db.add(record)
            await db.flush()
        if record.status == STATUS_CLAIMED:
            continue
        target = task.num or 1
        record.progress = min((record.progress or 0) + num, target)
        if record.progress >= target:
            record.status = STATUS_CLAIMABLE
        record.updated_time = datetime.datetime.now()
        updated.append(record)
    return updated


@router.get("/user/tasks")
async def get_tasks(user: User = Depends(current_user), db: AsyncSession = Depends(get_db_readonly)):
    """Get all tasks with the current user's progress, grouped by category."""
    today = datetime.date.today()

    result = await db.execute(
        select(Task).where(Task.status == 1).order_by(Task.category.asc(), Task.sort.asc(), Task.id.asc())
    )
    tasks = result.scalars().all()

    record_result = await db.execute(
        select(TaskRecord).where(
            TaskRecord.user_id == user.user_id,
            (TaskRecord.category != CATEGORY_DAILY) | (TaskRecord.task_date == today),
        )
    )
    records = record_result.scalars().all()

    signin_records = [r for r in records if r.category == CATEGORY_SIGNIN]
    latest_signin = max(signin_records, key=lambda r: (r.task_date, r.id), default=None)

    signed_today = latest_signin is not None and latest_signin.task_date == today
    if latest_signin is None or latest_signin.task_date < today - datetime.timedelta(days=1):
        streak_day = 0
    else:
        streak_day = latest_signin.progress or 0

    record_map = {}
    for r in records:
        if r.category in (CATEGORY_DAILY, CATEGORY_NEWCOMER):
            record_map[r.task_id] = r

    signin_items = []
    daily_items = []
    newcomer_items = []
    for task in tasks:
        item = task.to_dict()
        if task.category == CATEGORY_SIGNIN:
            item["status"] = STATUS_CLAIMED if task.num <= streak_day else STATUS_DOING
            signin_items.append(item)
        elif task.category == CATEGORY_DAILY:
            record = record_map.get(task.id)
            item["progress"] = record.progress if record else 0
            item["status"] = record.status if record else STATUS_DOING
            daily_items.append(item)
        else:
            record = record_map.get(task.id)
            item["progress"] = record.progress if record else 0
            item["status"] = record.status if record else STATUS_DOING
            newcomer_items.append(item)

    return {
        "code": 200,
        "data": {
            "signin": {
                "signed_today": signed_today,
                "current_day": streak_day,
                "cycle_days": SIGNIN_CYCLE_DAYS,
                "items": signin_items,
            },
            "daily": daily_items,
            "newcomer": newcomer_items,
        },
    }


@router.post("/user/signin")
async def signin(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Sign in for the current user. 7-day cycle, streak resets if a day is missed."""
    today = datetime.date.today()

    result = await db.execute(
        select(TaskRecord)
        .where(TaskRecord.user_id == user.user_id, TaskRecord.category == CATEGORY_SIGNIN)
        .order_by(TaskRecord.task_date.desc(), TaskRecord.id.desc())
    )
    latest = result.scalars().first()

    if latest and latest.task_date == today:
        return {"code": 400, "msg": "今天已经签到过了"}

    if latest and latest.task_date == today - datetime.timedelta(days=1):
        day = (latest.progress or 0) % SIGNIN_CYCLE_DAYS + 1
    else:
        day = 1

    task_result = await db.execute(
        select(Task).where(Task.category == CATEGORY_SIGNIN, Task.num == day, Task.status == 1)
    )
    task = task_result.scalars().first()
    if not task:
        raise HTTPException(status_code=500, detail=f"第{day}天的签到任务未配置")

    record = TaskRecord(
        user_id=user.user_id,
        task_id=task.id,
        category=CATEGORY_SIGNIN,
        progress=day,
        status=STATUS_CLAIMED,
        task_date=today,
    )
    db.add(record)
    _grant_reward(user, task)

    return {
        "code": 200,
        "data": {
            "day": day,
            "reward": _reward_dict(task),
        },
    }


@router.post("/user/task/report")
async def report_task_progress(data: TaskReportRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Report a task event (e.g. follow an anchor) to increase task progress."""
    if data.type == "signin":
        return {"code": 400, "msg": "签到任务请调用 /api/user/signin"}
    updated = await add_task_progress(db, user.user_id, data.type, data.num)
    items = [
        {"task_id": r.task_id, "progress": r.progress, "status": r.status}
        for r in updated
    ]
    return {"code": 200, "data": items}


@router.post("/user/task/receive")
async def receive_task_reward(data: TaskReceiveRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Claim the reward of a completed daily/newcomer task."""
    task = await db.get(Task, data.task_id)
    if not task or task.status != 1:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.category == CATEGORY_SIGNIN:
        return {"code": 400, "msg": "签到奖励在签到时自动发放"}

    today = datetime.date.today()
    record = await _get_record(db, user.user_id, task, today)
    if not record or record.status == STATUS_DOING:
        return {"code": 400, "msg": "任务还未完成"}
    if record.status == STATUS_CLAIMED:
        return {"code": 400, "msg": "奖励已领取过了"}

    record.status = STATUS_CLAIMED
    record.updated_time = datetime.datetime.now()
    _grant_reward(user, task)

    return {"code": 200, "data": {"reward": _reward_dict(task)}}
