"""
Google Play Real-Time Developer Notifications (RTDN) webhook.

Receives Pub/Sub push messages from Google Play. Configure the push endpoint as:
    https://<host>/api/google/rtdn?secret=<RTDN_SECRET>
(or pass the secret via the `x-rtdn-secret` header when using an intermediate proxy).

Requires the `RTDN_SECRET` env var; the endpoint is disabled until it is set.
"""
import base64
import hmac
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.google_play import GooglePlayError
from app.google_refund import handle_canceled_one_time_purchase, handle_voided_purchase_token

# Use Uvicorn's configured handler so successful RTDN events appear in Fly logs.
logger = logging.getLogger("uvicorn.error.rtdn")
router = APIRouter(prefix="/api/google", tags=["rtdn"])
REFUND_TYPE_FULL = 1
REFUND_TYPE_PARTIAL = 2
ONE_TIME_PRODUCT_CANCELED = 2


def _decode_pubsub_message(body: dict) -> Optional[dict]:
    """Accept both Pub/Sub's wrapped push body and its unwrapped JSON payload."""
    if not isinstance(body, dict):
        return None
    if "message" not in body and "packageName" in body:
        return body

    message = body.get("message")
    if not isinstance(message, dict):
        return None
    data_b64 = message.get("data")
    if not data_b64:
        return None
    try:
        payload = json.loads(base64.b64decode(data_b64, validate=True))
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


@router.post("/rtdn")
async def receive_rtdn(request: Request):
    """Handle a Google Play RTDN push notification.

    Responds 200 quickly; unknown/unmatchable notifications are acknowledged
    silently, while unexpected processing errors surface as 500 so Pub/Sub
    retries with backoff.
    """
    secret = os.environ.get("RTDN_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="RTDN endpoint is disabled")
    provided = request.query_params.get("secret") or request.headers.get("x-rtdn-secret")
    if not provided or not hmac.compare_digest(provided.encode(), secret.encode()):
        logger.warning("rtdn: rejected request with bad secret from %s", request.client.host if request.client else "?")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    payload = _decode_pubsub_message(body)
    if payload is None:
        logger.warning("rtdn: ignored malformed or unsupported Pub/Sub payload")
        return {"code": 200}

    package_name = payload.get("packageName")

    if "testNotification" in payload:
        logger.info("rtdn: test notification received for %s", package_name)
        return {"code": 200}

    voided = payload.get("voidedPurchaseNotification")
    if isinstance(voided, dict):
        purchase_token = voided.get("purchaseToken")
        refund_type = voided.get("refundType")
        has_purchase_reference = all(isinstance(value, str) and value for value in (package_name, purchase_token))
        logger.info(
            "rtdn: voided purchase pkg=%s orderId=%s refundType=%s",
            package_name, voided.get("orderId"), refund_type,
        )
        if refund_type == REFUND_TYPE_PARTIAL:
            logger.warning("rtdn: partial refund requires manual review, pkg=%s", package_name)
        elif type(refund_type) is not int or refund_type != REFUND_TYPE_FULL:
            logger.warning("rtdn: ignored unexpected refund type, pkg=%s", package_name)
        elif not has_purchase_reference:
            logger.warning("rtdn: full refund missing package name or purchase token")
        else:
            await handle_voided_purchase_token(purchase_token, package_name)
        return {"code": 200}

    otp = payload.get("oneTimeProductNotification")
    if isinstance(otp, dict):
        notification_type = otp.get("notificationType")
        purchase_token = otp.get("purchaseToken")
        sku = otp.get("sku")
        logger.info(
            "rtdn: one-time product notification type=%s sku=%s pkg=%s",
            notification_type, sku, package_name,
        )
        if notification_type == ONE_TIME_PRODUCT_CANCELED and all(
            isinstance(value, str) and value for value in (package_name, purchase_token, sku)
        ):
            try:
                await handle_canceled_one_time_purchase(purchase_token, package_name, sku)
            except GooglePlayError as exc:
                logger.warning("rtdn: Google cancellation check failed for pkg=%s sku=%s: %s", package_name, sku, exc)
                raise HTTPException(status_code=502, detail="Google cancellation check failed") from exc
        return {"code": 200}

    sub = payload.get("subscriptionNotification")
    if isinstance(sub, dict):
        logger.info("rtdn: subscription notification type=%s pkg=%s", sub.get("subscriptionType"), package_name)
        return {"code": 200}

    logger.info("rtdn: unhandled notification for %s", package_name)
    return {"code": 200}
