"""
Google Play refund (voided purchase) handling.

Processes voided purchase tokens received through RTDN or a manual processing
pass, matches them against paid orders, and revokes the assets (diamonds / VIP
days / cards) that were granted on verification.
"""
import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import google_play
from app.google_play import GooglePlayError
from app.database import AsyncSessionLocal
from app.models import Order, User, Product, AppList
from app.models.order import ORDER_STATUS_PAID, ORDER_STATUS_REFUNDED
from app.models.transaction import (
    ASSET_DIAMOND, ASSET_VIP, ASSET_CALL_CARD, ASSET_MATCH_CARD, ASSET_CHAT_CARD,
    TRANSACTION_REFUND,
)
from app.tools import add_transaction, send_system_chat_message
from app.product_selection import get_product_for_order

logger = logging.getLogger("uvicorn.error.google_refund")

MAX_PAGES_PER_PACKAGE = 5


async def _collect_package_names(db: AsyncSession) -> list:
    """Package names to poll: online apps first, then any seen on orders."""
    packages = []
    result = await db.execute(select(AppList.package_name).where(AppList.is_online == True))  # noqa: E712
    packages.extend(result.scalars().all())
    result = await db.execute(select(Order.package_name).where(Order.package_name != None).distinct())  # noqa: E712
    packages.extend(result.scalars().all())
    return list(dict.fromkeys(p for p in packages if p))


async def _revoke_order_assets(db: AsyncSession, order: Order, product: Product) -> int:
    """Revoke the granted assets and return the number of diamonds actually deducted."""
    result = await db.execute(select(User).where(User.user_id == order.user_id).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        raise RuntimeError(f"Refund user not found for order {order.order_no}")

    now_ts = int(time.time())

    diamond_grant = order.google_granted_diamonds
    if diamond_grant is None:
        # Old orders only received the base amount and have no snapshot.
        diamond_grant = product.diamonds or 0
    available = max(0, user.balance or 0)
    diamonds_revoked = min(available, max(0, diamond_grant))
    if diamonds_revoked:
        user.balance = available - diamonds_revoked
        await add_transaction(user, -diamonds_revoked, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_REFUND, db=db)

    if product.vip_days and product.vip_days > 0:
        current_expire = user.vip_expire_time
        if current_expire:
            new_expire = current_expire - product.vip_days * 86400
            user.vip_expire_time = max(new_expire, now_ts)
            await add_transaction(user, -product.vip_days, asset_type=ASSET_VIP, transaction_type=TRANSACTION_REFUND, db=db)

    if product.call_card_num and product.call_card_num > 0:
        revoked = min(user.call_card_num or 0, product.call_card_num)
        user.call_card_num = (user.call_card_num or 0) - revoked
        if revoked > 0:
            await add_transaction(user, -revoked, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_REFUND, db=db)

    if product.match_card_num and product.match_card_num > 0:
        revoked = min(user.match_card_num or 0, product.match_card_num)
        user.match_card_num = (user.match_card_num or 0) - revoked
        if revoked > 0:
            await add_transaction(user, -revoked, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_REFUND, db=db)

    if product.chat_card_num and product.chat_card_num > 0:
        revoked = min(user.chat_card_num or 0, product.chat_card_num)
        user.chat_card_num = (user.chat_card_num or 0) - revoked
        if revoked > 0:
            await add_transaction(user, -revoked, asset_type=ASSET_CHAT_CARD, transaction_type=TRANSACTION_REFUND, db=db)

    return diamonds_revoked


async def _process_voided_token(purchase_token: str, package_name: str | None = None) -> Optional[dict]:
    """Revoke assets for a single voided purchase token. Returns a summary dict."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Order).where(Order.purchase_token == purchase_token).with_for_update()
            )
            order = result.scalar_one_or_none()
            if not order:
                logger.info("refund: no local order matched the Google purchase, package=%s", package_name)
                return None
            if package_name is not None and order.package_name != package_name:
                logger.warning("refund: package mismatch for order %s, package=%s", order.order_no, package_name)
                return None
            if order.order_status != ORDER_STATUS_PAID:
                logger.info("refund: skipping order %s with status %s", order.order_no, order.order_status)
                return None

            product = await get_product_for_order(db, order)
            if not product:
                raise RuntimeError(f"Refund product not found for order {order.order_no}")

            diamonds_revoked = await _revoke_order_assets(db, order, product)

            order.order_status = ORDER_STATUS_REFUNDED
            order.updated_time = int(time.time())
            db.add(order)
            message = f"Your Google Play order {order.order_no} was refunded."
            if diamonds_revoked:
                unit = "diamond was" if diamonds_revoked == 1 else "diamonds were"
                message += f" {diamonds_revoked} {unit} deducted from your balance."
            await send_system_chat_message(db, order.user_id, message)
            detail = {
                "order_no": order.order_no, "user_id": order.user_id, "sku": order.sku,
                "diamonds_revoked": diamonds_revoked,
            }
            await db.commit()
            logger.info("refund processed: order_no=%s diamonds_revoked=%s", detail["order_no"], diamonds_revoked)
            return detail
        except Exception:
            await db.rollback()
            raise


async def handle_voided_purchase_token(purchase_token: str, package_name: str | None = None) -> Optional[dict]:
    """Public entry: revoke assets for a voided (refunded) purchase token. Idempotent."""
    return await _process_voided_token(purchase_token, package_name)


async def handle_canceled_one_time_purchase(purchase_token: str, package_name: str, sku: str) -> Optional[dict]:
    """Check a cancellation against Google before treating a credited order as revoked."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Order.order_no).where(
            Order.purchase_token == purchase_token,
            Order.package_name == package_name,
            Order.sku == sku,
            Order.order_status == ORDER_STATUS_PAID,
        ))
        order_no = result.scalar_one_or_none()
    if order_no is None:
        # Pending purchases never delivered anything; duplicate events also land here.
        logger.info("refund: cancellation did not match a paid order, package=%s sku=%s", package_name, sku)
        return None

    purchase = await google_play.verify_purchase(package_name, sku, purchase_token)
    if purchase.get("purchaseState") != google_play.PURCHASE_STATE_CANCELED:
        logger.info("refund: cancellation not confirmed by Google, order_no=%s", order_no)
        return None
    return await _process_voided_token(purchase_token, package_name)


async def reconcile_refunded_order(order_no: str) -> Optional[dict]:
    """Manually revoke one explicitly selected order after confirming a full refund."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Order).where(Order.order_no == order_no))
        order = result.scalar_one_or_none()
        if not order or order.order_status != ORDER_STATUS_PAID:
            return None
        package_name, google_order_id, purchase_token = order.package_name, order.google_order_id, order.purchase_token
    if not (package_name and google_order_id and purchase_token):
        return None

    purchase = await google_play.get_order(package_name, google_order_id)
    if (
        purchase.get("state") != "REFUNDED"
        or purchase.get("orderId") != google_order_id
        or purchase.get("purchaseToken") != purchase_token
    ):
        return None
    return await _process_voided_token(purchase_token, package_name)


async def process_refunds_once() -> dict:
    """Run one manual refund reconciliation pass over all packages."""
    summary = {"packages": 0, "voided_checked": 0, "refunded": 0, "errors": 0, "details": []}

    async with AsyncSessionLocal() as db:
        try:
            packages = await _collect_package_names(db)
        except Exception:
            logger.exception("refund: failed to collect package names")
            summary["errors"] += 1
            return summary

    for package_name in packages:
        summary["packages"] += 1
        page_token = None
        for _page in range(MAX_PAGES_PER_PACKAGE):
            try:
                resp = await google_play.list_voided_purchases(package_name, page_token=page_token)
            except GooglePlayError as e:
                logger.error("refund: failed to list voided purchases for %s: %s", package_name, e)
                summary["errors"] += 1
                break

            voided = resp.get("voidedPurchases") or []
            for item in voided:
                summary["voided_checked"] += 1
                purchase_token = item.get("purchaseToken")
                if not purchase_token or "voidedQuantity" in item:
                    continue
                try:
                    detail = await _process_voided_token(purchase_token, package_name)
                except Exception:
                    logger.exception("refund: failed to process voided purchase for %s", package_name)
                    summary["errors"] += 1
                    continue
                if detail:
                    summary["refunded"] += 1
                    summary["details"].append(detail)

            page_token = (resp.get("tokenPagination") or {}).get("nextPageToken")
            if not page_token:
                break

    return summary


