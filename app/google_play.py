"""
Google Play Developer API client.

Handles OAuth2 access token management (service account or static env token),
in-app purchase verification, and voided purchases (refunds) listing.
"""
import asyncio
import logging
import os
import time
from typing import Optional

import httpx

from app.logging_config import log_event
from app.tools import get_http_client

logger = logging.getLogger(__name__)

BASE_URL = "https://androidpublisher.googleapis.com/androidpublisher/v3"

PURCHASE_STATE_PURCHASED = 0
PURCHASE_STATE_CANCELED = 1
PURCHASE_STATE_PENDING = 2


class GooglePlayError(Exception):
    """Raised when a Google Play Developer API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


_token_lock = asyncio.Lock()
_cached_token: Optional[str] = None
_cached_token_expiry: float = 0.0


def _refresh_service_account_token(sa_file: str) -> tuple[Optional[str], float]:
    """Synchronously refresh a service account token (runs in a worker thread)."""
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest
    except Exception:
        log_event(logger, logging.ERROR, "google.auth.failed", reason="dependency_missing", exc_info=True)
        raise GooglePlayError(
            "google-auth not installed; add `google-auth` to requirements to use service account verification"
        )

    try:
        scopes = ["https://www.googleapis.com/auth/androidpublisher"]
        creds = service_account.Credentials.from_service_account_file(sa_file, scopes=scopes)
        creds.refresh(GoogleRequest())
        expiry_ts = creds.expiry.timestamp() if getattr(creds, "expiry", None) else time.time() + 3600
        return creds.token, expiry_ts
    except Exception:
        log_event(logger, logging.ERROR, "google.auth.failed", reason="token_refresh", exc_info=True)
        raise GooglePlayError("failed to obtain service account token")


async def get_google_access_token() -> Optional[str]:
    """Return an access token from cache, service account, or env var.

    Uses `GOOGLE_SERVICE_ACCOUNT_FILE` (path to JSON key file) if set,
    otherwise falls back to `GOOGLE_ACCESS_TOKEN` env var. The service
    account refresh runs in a worker thread so it never blocks the loop.
    """
    global _cached_token, _cached_token_expiry

    async with _token_lock:
        now = time.time()
        if _cached_token and now + 60 < _cached_token_expiry:
            return _cached_token

        sa_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        if sa_file and os.path.exists(sa_file):
            token, expiry_ts = await asyncio.to_thread(_refresh_service_account_token, sa_file)
            if token:
                _cached_token = token
                _cached_token_expiry = expiry_ts
                return token

        return os.environ.get("GOOGLE_ACCESS_TOKEN") or None


async def _google_api_get(url: str, *, operation: str, params: Optional[dict] = None) -> dict:
    """Authenticated GET against the Play Developer API, returns parsed JSON."""
    access_token = await get_google_access_token()
    if not access_token:
        log_event(logger, logging.ERROR, "google.auth.failed", reason="not_configured", operation=operation)
        raise GooglePlayError("Google verification not configured (missing token or service account file)")

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        client = await get_http_client()
        resp = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as e:
        log_event(logger, logging.ERROR, "google.api.failed", operation=operation, error_type=type(e).__name__)
        raise GooglePlayError("HTTP request to Google failed")

    if resp.status_code == 401:
        # Token may have been revoked/expired; force a refresh on next call.
        global _cached_token, _cached_token_expiry
        async with _token_lock:
            _cached_token = None
            _cached_token_expiry = 0.0

    if resp.status_code != 200:
        # Purchase tokens appear in verification URLs and can be echoed in errors.
        log_event(logger, logging.ERROR, "google.api.failed", operation=operation, google_status=resp.status_code)
        raise GooglePlayError(f"Google API request failed: {resp.status_code}", status_code=resp.status_code)

    try:
        return resp.json()
    except Exception:
        log_event(logger, logging.ERROR, "google.api.failed", operation=operation, reason="invalid_json", exc_info=True)
        raise GooglePlayError("failed to parse Google response")


def get_purchase_order_id(payload: dict) -> Optional[str]:
    """Read the Google order ID when present in a Google API response or notification."""
    order_id = payload.get("orderId")
    if not isinstance(order_id, str):
        return None
    return order_id.strip() or None


async def verify_purchase(package_name: str, product_id: str, purchase_token: str) -> dict:
    """Verify an in-app product purchase. Returns the raw Google response."""
    url = f"{BASE_URL}/applications/{package_name}/purchases/products/{product_id}/tokens/{purchase_token}"
    return await _google_api_get(url, operation="verify_purchase")


async def get_order(package_name: str, google_order_id: str) -> dict:
    """Read the payment state of a specific Google Play order."""
    return await _google_api_get(f"{BASE_URL}/applications/{package_name}/orders/{google_order_id}", operation="get_order")


async def list_voided_purchases(
    package_name: str,
    page_token: Optional[str] = None,
    max_results: int = 200,
) -> dict:
    """List voided (refunded/revoked) purchases for an app.

    Returns the raw Google response containing `voidedPurchases` and
    optionally `tokenPagination.nextPageToken`. Partial refunds are excluded.
    """
    params = {"maxResults": max_results, "includeQuantityBasedPartialRefund": "false"}
    if page_token:
        params["token"] = page_token
    url = f"{BASE_URL}/applications/{package_name}/purchases/voidedpurchases"
    return await _google_api_get(url, operation="list_voided_purchases", params=params)
