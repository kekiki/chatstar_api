import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Transaction

_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(verify=False, timeout=30.0)
    return _http_client


def add_transaction(user_id: int, amount: int, asset_type: int, transaction_type: int, db: AsyncSession):
    transaction = Transaction(user_id=user_id, amount=amount, asset_type=asset_type, transaction_type=transaction_type)
    db.add(transaction)
