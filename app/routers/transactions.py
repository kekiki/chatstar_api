from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_readonly
from app.models import Transaction, User
from app.security import current_user

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/user/transactions")
async def get_transactions(user: User = Depends(current_user), db: AsyncSession = Depends(get_db_readonly)):
    """Get all transactions for the current user."""
    result = await db.execute(select(Transaction).where(Transaction.user_id == user.user_id).order_by(Transaction.created_time.desc()))
    transactions = result.scalars().all()
    items = [transaction.to_dict() for transaction in transactions]
    return {"code": 200, "data": items}
