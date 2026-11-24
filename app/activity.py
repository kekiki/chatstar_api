import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.database import AsyncSessionLocal
from app.models import DailyUserActivity

logger = logging.getLogger(__name__)
REPORT_TZ = ZoneInfo("Asia/Shanghai")
# The database key deduplicates across workers. The local cache avoids writes
# for subsequent requests from the same user.
_tracked_date: date | None = None
_tracked_users: set[int] = set()


def _untracked_activity_date(user_id: int, is_anchor: bool | None) -> date | None:
    global _tracked_date
    if is_anchor:
        return None
    stat_date = datetime.now(REPORT_TZ).date()
    if _tracked_date != stat_date:
        _tracked_users.clear()
        _tracked_date = stat_date
    return stat_date if user_id not in _tracked_users else None


def schedule_user_activity(tasks: BackgroundTasks, user_id: int, is_anchor: bool | None) -> None:
    stat_date = _untracked_activity_date(user_id, is_anchor)
    if stat_date is not None:
        tasks.add_task(record_user_activity, stat_date, user_id)


async def track_user_activity(user_id: int, is_anchor: bool | None) -> None:
    stat_date = _untracked_activity_date(user_id, is_anchor)
    if stat_date is not None:
        await record_user_activity(stat_date, user_id)


async def record_user_activity(stat_date: date, user_id: int) -> None:
    if stat_date == _tracked_date and user_id in _tracked_users:
        return
    try:
        async with AsyncSessionLocal.begin() as db:
            insert = sqlite_insert if db.bind.dialect.name == "sqlite" else postgres_insert
            await db.execute(
                insert(DailyUserActivity).values(stat_date=stat_date, user_id=user_id)
                .on_conflict_do_nothing(index_elements=["stat_date", "user_id"])
            )
    except (OSError, SQLAlchemyError):
        logger.exception("Failed to record daily user activity")
        return
    if stat_date == _tracked_date:
        if len(_tracked_users) >= 100_000:
            _tracked_users.pop()
        _tracked_users.add(user_id)
