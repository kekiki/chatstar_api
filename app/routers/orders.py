"""
Order routes: create order, query by orderNo, query by userId, verify Google purchase.
"""

from typing import List, Optional
import time
import uuid
import os
import logging

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order
from app.schemas.order_request import CreateOrderRequest, VerifyGoogleRequest

logger = logging.getLogger("orders")
router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/order/create")
def create_order(data: CreateOrderRequest, db: Session = Depends(get_db)):
    """Create a new order record."""
    order_no = data.orderNo or f"local-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    existing = db.query(Order).filter(Order.orderNo == order_no).first()
    if existing:
        raise HTTPException(status_code=400, detail="orderNo already exists")

    order = Order(
        userId=data.userId,
        orderNo=order_no,
        productId=data.productId,
        productType=data.productType,
        currencyCode=data.currencyCode,
        currencyPrice=data.currencyPrice,
        vipDays=data.vipDays,
        callCardNum=data.callCardNum,
        matchCardNum=data.matchCardNum,
        chatCardNum=data.chatCardNum,
        createdAt=int(time.time())
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {"code": 200, "data": order.to_dict()}


@router.get("/order/{orderNo}")
def get_order(orderNo: str, db: Session = Depends(get_db)):
    """Get an order by its orderNo."""
    order = db.query(Order).filter(Order.orderNo == orderNo).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"code": 200, "data": order.to_dict()}


@router.get("/orders/user/{userId}")
def get_orders_by_user(userId: int, db: Session = Depends(get_db)):
    """Get all orders for a given userId."""
    rows: List[Order] = db.query(Order).filter(Order.userId == userId).order_by(Order.id.desc()).all()
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
    # return cached token if valid
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
            # cache token a bit earlier than expiry
            _cached_token = token
            _cached_token_expiry = expiry_ts
            return token
        except Exception as e:
            logger.exception("failed to obtain service account token: %s", e)
            raise RuntimeError("failed to obtain service account token")

    # fallback to env var
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


@router.post("/order/verifyGoogle")
def verify_google_order(data: VerifyGoogleRequest, db: Session = Depends(get_db)):
    """Verify a Google Play in-app purchase and update order status.

    Expects `GOOGLE_ACCESS_TOKEN` env var to be set with a valid OAuth2 token.
    """
    try:
        result = _verify_google_purchase_with_api(data.packageName, data.productId, data.purchaseToken)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Example: response contains `purchaseState` (0 = purchased)
    purchase_state = result.get("purchaseState")

    order = db.query(Order).filter(Order.orderNo == data.orderNo).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if purchase_state == 0:
        order.orderStatus = 1  # mark paid
        db.add(order)
        db.commit()
        db.refresh(order)

    return {"code": 200, "data": {"verified": purchase_state == 0, "google": result}}
