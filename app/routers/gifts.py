from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import asc

from app.database import get_db_readonly
from app.models import Gift, User
from app.security import current_user

router = APIRouter(prefix="/api", tags=["gifts"])


@router.get("/config/gifts")
async def get_gifts(user: User = Depends(current_user), db: AsyncSession = Depends(get_db_readonly)):
    """Get all gifts sorted by price."""
    result = await db.execute(select(Gift).order_by(asc(Gift.gift_price)))
    gifts = result.scalars().all()
    items = [gift.to_dict() for gift in gifts]
    return {"code": 200, "data": items}
