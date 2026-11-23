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

from app.google_play import GooglePlayError, get_purchase_order_id
from app.google_refund import handle_canceled_one_time_purchase, handle_voided_purchase_token
from app.logging_config import log_event

logger = logging.getLogger(__name__)
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
        log_event(logger, logging.ERROR, "rtdn.rejected", reason="endpoint_disabled")
        raise HTTPException(status_code=503, detail="RTDN endpoint is disabled")
    provided = request.query_params.get("secret") or request.headers.get("x-rtdn-secret")
    if not provided or not hmac.compare_digest(provided.encode(), secret.encode()):
        log_event(logger, logging.WARNING, "rtdn.rejected", reason="invalid_secret")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        body = await request.json()
    except (ValueError, UnicodeError):
        log_event(logger, logging.WARNING, "rtdn.rejected", reason="invalid_json")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    payload = _decode_pubsub_message(body)
    if payload is None:
        log_event(logger, logging.WARNING, "rtdn.ignored", reason="invalid_payload")
        return {"code": 200}

    package_name = payload.get("packageName")

    if "testNotification" in payload:
        log_event(logger, logging.INFO, "rtdn.test_received", package_name=package_name)
        return {"code": 200}

    voided = payload.get("voidedPurchaseNotification")
    if isinstance(voided, dict):
        purchase_token = voided.get("purchaseToken")
        refund_type = voided.get("refundType")
        has_purchase_reference = all(isinstance(value, str) and value for value in (package_name, purchase_token))
        google_order_id = get_purchase_order_id(voided)
        context = {"package_name": package_name, "google_order_id": google_order_id, "refund_type": refund_type}
        log_event(logger, logging.INFO, "rtdn.voided_received", **context)
        if refund_type == REFUND_TYPE_PARTIAL:
            log_event(logger, logging.WARNING, "rtdn.ignored", reason="partial_refund", **context)
        elif type(refund_type) is not int or refund_type != REFUND_TYPE_FULL:
            log_event(logger, logging.WARNING, "rtdn.ignored", reason="unexpected_refund_type", **context)
        elif not has_purchase_reference:
            log_event(logger, logging.WARNING, "rtdn.ignored", reason="missing_purchase_reference", **context)
        else:
            await handle_voided_purchase_token(purchase_token, package_name, google_order_id)
        return {"code": 200}

    otp = payload.get("oneTimeProductNotification")
    if isinstance(otp, dict):
        notification_type = otp.get("notificationType")
        purchase_token = otp.get("purchaseToken")
        sku = otp.get("sku")
        context = {"package_name": package_name, "sku": sku, "notification_type": notification_type}
        log_event(logger, logging.INFO, "rtdn.one_time_received", **context)
        if notification_type == ONE_TIME_PRODUCT_CANCELED and all(
            isinstance(value, str) and value for value in (package_name, purchase_token, sku)
        ):
            try:
                await handle_canceled_one_time_purchase(purchase_token, package_name, sku)
            except GooglePlayError as exc:
                log_event(logger, logging.WARNING, "rtdn.cancellation_check_failed", google_status=exc.status_code, **context)
                raise HTTPException(status_code=502, detail="Google cancellation check failed") from exc
        return {"code": 200}

    sub = payload.get("subscriptionNotification")
    if isinstance(sub, dict):
        log_event(logger, logging.INFO, "rtdn.subscription_received",
                  notification_type=sub.get("subscriptionType"), package_name=package_name)
        return {"code": 200}

    log_event(logger, logging.INFO, "rtdn.ignored", reason="unhandled_type", package_name=package_name)
    return {"code": 200}
