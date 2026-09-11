"""
Order routes: create order, query by orderNo, query by userId, verify Google purchase.
"""

import logging
import os
from datetime import datetime
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_readonly
from app.models import Order, User, Product
from app.models.transaction import ASSET_DIAMOND, ASSET_VIP, ASSET_CALL_CARD, ASSET_MATCH_CARD, ASSET_CHAT_CARD, TRANSACTION_PURCHASE
from app.schemas.orders import CreateOrderRequest, VerifyGoogleRequest
from app.security import current_user, current_user_readonly
from app.tools import get_http_client, add_transaction
from app.models.task import TYPE_RECHARGE_TIMES, TYPE_UNLOCK_VIP, TYPE_FIRST_RECHARGE

logger = logging.getLogger("orders")
router = APIRouter(prefix="/api", tags=["orders"])

@router.get("/order/products")
async def get_products(request: Request, db: AsyncSession = Depends(get_db_readonly)):
    """Get product list filtered by package_name from request header."""
    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package-name header")
    
    result = await db.execute(select(Product).where(Product.package_name == package_name).order_by(Product.diamonds, Product.vip_days))
    products = result.scalars().all()
    items = [product.to_dict() for product in products]
    return {"code": 200, "data": items}


@router.post("/order/create")
async def create_order(request: Request, data: CreateOrderRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Create a new order record."""
    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")
    
    now = datetime.now()
    transaction_no = f"cs-{now.year}-{now.month}-{now.day}-{now.hour}-{now.minute}-{now.second}-{now.microsecond}"
    order_no = f"O{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    agent = request.headers.get("user-agent")

    order = Order(
        package_name=package_name,
        user_id=user.user_id,
        transaction_no=transaction_no,
        order_no=order_no,
        sku=data.sku,
        type=data.type,
        pp_id=data.pp_id,
        anchor_id=data.anchor_id,
        path=data.path,
        order_status=0,
        agent=agent,
        created_time=int(time.time()),
    )
    db.add(order)
    await db.flush()
    return {"code": 200, "data": order.to_dict()}

@router.get("/user/orders")
async def get_user_orders(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
):
    """Get paginated orders for the current user, sorted by created_time desc."""
    base_query = select(Order).where(Order.user_id == user.user_id)
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(Order.created_time.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    orders = result.scalars().all()
    items = [order.to_dict() for order in orders]
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


_cached_token = None
_cached_token_expiry = 0.0


def _get_google_access_token() -> Optional[str]:
    """Return an access token either from a service account file or from env var.

    If `GOOGLE_SERVICE_ACCOUNT_FILE` is set (path to JSON key file), use it to
    obtain an access token with the `androidpublisher` scope. Otherwise fall
    back to `GOOGLE_ACCESS_TOKEN` env var.
    """
    global _cached_token, _cached_token_expiry

    now = time.time()
    if _cached_token and now + 60 < _cached_token_expiry:
        return _cached_token

    sa_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if sa_file and os.path.exists(sa_file):
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request as GoogleRequest
        except Exception:
            logger.exception("google-auth library missing")
            raise RuntimeError(
                "google-auth not installed; add `google-auth` to requirements to use service account verification"
            )
        try:
            scopes = ["https://www.googleapis.com/auth/androidpublisher"]
            creds = service_account.Credentials.from_service_account_file(sa_file, scopes=scopes)
            creds.refresh(GoogleRequest())
            token = creds.token
            expiry_ts = creds.expiry.timestamp() if getattr(creds, "expiry", None) else now + 3600
            _cached_token = token
            _cached_token_expiry = expiry_ts
            return token
        except Exception as e:
            logger.exception("failed to obtain service account token: %s", e)
            raise RuntimeError("failed to obtain service account token")

    token = os.environ.get("GOOGLE_ACCESS_TOKEN")
    if token:
        return token
    return None


async def _verify_google_purchase_with_api(package_name: str, product_id: str, token: str) -> dict:
    access_token = _get_google_access_token()
    if not access_token:
        logger.error("Google verification not configured: no token available")
        raise RuntimeError("Google verification not configured (missing token or service account file)")

    url = (
        f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package_name}"
        f"/purchases/products/{product_id}/tokens/{token}"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        client = await get_http_client()
        resp = await client.get(url, headers=headers)
    except Exception as e:
        logger.exception("HTTP request to Google failed: %s", e)
        raise RuntimeError("HTTP request to Google failed")

    if resp.status_code != 200:
        logger.error("Google verification failed status=%s body=%s", resp.status_code, resp.text)
        raise RuntimeError(f"Google verification failed: {resp.status_code} {resp.text}")

    try:
        return resp.json()
    except Exception:
        logger.exception("failed to parse Google response JSON")
        raise RuntimeError("failed to parse Google response")


@router.post("/order/verify")
async def verify_google_order(data: VerifyGoogleRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Verify a Google Play in-app purchase and update order status.

    Expects `GOOGLE_ACCESS_TOKEN` env var to be set with a valid OAuth2 token.
    """
    try:
        result = await _verify_google_purchase_with_api(data.package_name, data.product_id, data.purchase_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    purchase_state = result.get("purchaseState")

    result_product = await db.execute(select(Product).where(Product.sku == data.product_id))
    product = result_product.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    result_order = await db.execute(select(Order).where(Order.order_no == data.order_no, Order.user_id == user.user_id))
    order = result_order.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if purchase_state == 0:
        order.order_status = 1
        db.add(order)
        
        from app.routers.tasks import add_task_progress
        task_type = TYPE_UNLOCK_VIP if order.isVip() else TYPE_RECHARGE_TIMES
        await add_task_progress(db, user.user_id, task_type, 1)
        if user.total == 0:
            await add_task_progress(db, user.user_id, TYPE_FIRST_RECHARGE, 1)
        
        user.balance = (user.balance or 0) + (product.diamonds or 0)
        if product.diamonds and product.diamonds > 0:
            add_transaction(user, product.diamonds, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_PURCHASE, db=db)
            user.total = (user.total or 0) + product.diamonds

        if product.vip_days and product.vip_days > 0:
            now_ts = int(time.time())
            current_expire = user.vip_expire_time or now_ts
            base = max(current_expire, now_ts)
            user.vip_expire_time = base + product.vip_days * 86400
            add_transaction(user, product.vip_days, asset_type=ASSET_VIP, transaction_type=TRANSACTION_PURCHASE, db=db)

        if product.call_card_num and product.call_card_num > 0:
            user.call_card_num = (user.call_card_num or 0) + product.call_card_num
            add_transaction(user, product.call_card_num, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_PURCHASE, db=db)

        if product.match_card_num and product.match_card_num > 0:
            user.match_card_num = (user.match_card_num or 0) + product.match_card_num
            add_transaction(user, product.match_card_num, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_PURCHASE, db=db)

        if product.chat_card_num and product.chat_card_num > 0:
            user.chat_card_num = (user.chat_card_num or 0) + product.chat_card_num
            add_transaction(user, product.chat_card_num, asset_type=ASSET_CHAT_CARD, transaction_type=TRANSACTION_PURCHASE, db=db)
        
        from app.tools import send_system_chat_message
        noti_msg = 'Congratulations! Your recharge was successful. '
        await send_system_chat_message(db,user.user_id,noti_msg)

    return {"code": 200, "data": {"verified": purchase_state == 0, "google": result}}
