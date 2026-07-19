"""
Order routes: create order, query by orderNo, query by userId, verify Google purchase.
"""

import logging
import os
from datetime import datetime
import time
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_readonly
from app.models import Order, User, Product
from app.schemas.order_request import CreateOrderRequest, VerifyGoogleRequest
from app.security import current_user, current_user_readonly

logger = logging.getLogger("orders")
router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/products")
async def get_products(request: Request, db: AsyncSession = Depends(get_db_readonly)):
    """Get product list filtered by package_name from request header."""
    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package-name header")
    
    result = await db.execute(select(Product).where(Product.package_name == package_name).order_by(Product.diamonds))
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
    transcation_no = f"cs-{now.year}-{now.month}-{now.day}-{now.minute}-{now.second}-{now.microsecond}"
    agent = request.headers.get("user-agent")

    order = Order(
        package_name=package_name,
        user_id=user.user_id,
        transcation_no=transcation_no,
        sku=data.sku,
        pp_id=data.pp_id,
        anchor_id=data.anchor_id,
        path=data.path,
        order_status=0,
        agent=agent,
        created_at=int(time.time()),
    )
    db.add(order)
    return {"code": 200, "data": order.to_dict()}


@router.get("/order/{order_no}")
async def get_order(order_no: str, user: User = Depends(current_user_readonly), db: AsyncSession = Depends(get_db_readonly)):
    """Get an order by its order_no."""
    result = await db.execute(select(Order).where(Order.order_no == order_no, Order.user_id == user.user_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"code": 200, "data": order.to_dict()}


@router.get("/orders/user/{user_id}")
async def get_orders_by_user(user_id: int, user: User = Depends(current_user_readonly), db: AsyncSession = Depends(get_db_readonly)):
    """Get all orders for a given user_id."""
    if user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    result = await db.execute(select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()))
    rows: List[Order] = result.scalars().all()
    items = [r.to_dict() for r in rows]
    return {"code": 200, "data": items}


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


def _verify_google_purchase_with_api(package_name: str, product_id: str, token: str) -> dict:
    """Verify Google Play in-app product purchase using Android Publisher API.

    Uses `_get_google_access_token()` to obtain a Bearer token.
    """
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
        resp = requests.get(url, headers=headers, timeout=10)
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
        result = _verify_google_purchase_with_api(data.package_name, data.product_id, data.purchase_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    purchase_state = result.get("purchaseState")

    result_order = await db.execute(select(Order).where(Order.order_no == data.order_no, Order.user_id == user.user_id))
    order = result_order.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if purchase_state == 0:
        order.order_status = 1
        db.add(order)

    return {"code": 200, "data": {"verified": purchase_state == 0, "google": result}}
