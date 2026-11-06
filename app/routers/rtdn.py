"""
Google Play Real-Time Developer Notifications (RTDN) webhook.

Receives Pub/Sub push messages from Google Play. Configure the push endpoint as:
    https://<host>/api/google/rtdn?secret=<RTDN_SECRET>
(or pass the secret via the `x-rtdn-secret` header when using an intermediate proxy).

Requires the `RTDN_SECRET` env var; the endpoint is disabled until it is set.
"""
import base64
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.google_refund import handle_voided_purchase_token

logger = logging.getLogger("rtdn")
router = APIRouter(prefix="/api/google", tags=["rtdn"])


def _decode_pubsub_message(body: dict) -> Optional[dict]:
    """Extract and base64-decode the RTDN payload from a Pub/Sub push body."""
    message = body.get("message")
    if not isinstance(message, dict):
        return None
    data_b64 = message.get("data")
    if not data_b64:
        return None
    try:
        return json.loads(base64.b64decode(data_b64))
    except Exception:
        logger.warning("rtdn: failed to decode message data")
        return None


@router.post("/rtdn")
async def receive_rtdn(request: Request):
    """Handle a Google Play RTDN push notification.

    Responds 200 quickly; unknown/unmatchable notifications are acknowledged
    silently (the refund polling loop remains the fallback), while unexpected
    processing errors surface as 500 so Pub/Sub retries with backoff.
    """
    secret = os.environ.get("RTDN_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="RTDN endpoint is disabled")
    provided = request.query_params.get("secret") or request.headers.get("x-rtdn-secret")
    if provided != secret:
        logger.warning("rtdn: rejected request with bad secret from %s", request.client.host if request.client else "?")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    payload = _decode_pubsub_message(body)
    if payload is None:
        return {"code": 200}

    package_name = payload.get("packageName")

    if "testNotification" in payload:
        logger.info("rtdn: test notification received for %s", package_name)
        return {"code": 200}

    voided = payload.get("voidedPurchaseNotification")
    if isinstance(voided, dict):
        purchase_token = voided.get("purchaseToken") or ""
        refund_type = voided.get("refundType")
        logger.info(
            "rtdn: voided purchase pkg=%s token=%s... refundType=%s",
            package_name, purchase_token[:32], refund_type,
        )
        if purchase_token and refund_type != 2:
            # refundType=2 为部分退款，不自动全额回收，留人工处理
            detail = await handle_voided_purchase_token(purchase_token)
            if detail:
                logger.info("rtdn: refund processed via rtdn: %s", detail)
        elif refund_type == 2:
            logger.warning(
                "rtdn: partial refund (refundType=2) skipped auto-revoke, needs manual review: pkg=%s token=%s...",
                package_name, purchase_token[:32],
            )
        return {"code": 200}

    otp = payload.get("oneTimeProductNotification")
    if isinstance(otp, dict):
        # 购买由 /api/order/verify 处理；取消态由客户端重新验证时落库，此处仅记录
        logger.info(
            "rtdn: one-time product notification type=%s sku=%s pkg=%s",
            otp.get("type"), otp.get("sku"), package_name,
        )
        return {"code": 200}

    sub = payload.get("subscriptionNotification")
    if isinstance(sub, dict):
        logger.info("rtdn: subscription notification type=%s pkg=%s", sub.get("subscriptionType"), package_name)
        return {"code": 200}

    logger.info("rtdn: unhandled notification for %s", package_name)
    return {"code": 200}
