from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_readonly
from app.models import Transaction, User
from app.security import current_user_readonly

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/user/transactions")
async def get_transactions(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
):
    """Get paginated transactions for the current user."""
    base_query = select(Transaction).where(Transaction.user_id == user.user_id)
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(Transaction.created_time.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    transactions = result.scalars().all()
    items = [transaction.to_dict() for transaction in transactions]
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
