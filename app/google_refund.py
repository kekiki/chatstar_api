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
from app.logging_config import log_event
from app.database import AsyncSessionLocal
from app.models import Order, User, Product, AppList
from app.models.order import ORDER_STATUS_PAID, ORDER_STATUS_REFUNDED
from app.models.transaction import (
    ASSET_DIAMOND, ASSET_VIP, ASSET_CALL_CARD, ASSET_MATCH_CARD, ASSET_CHAT_CARD,
    TRANSACTION_REFUND,
)
from app.tools import add_transaction, send_system_chat_message
from app.product_selection import get_product_for_order

logger = logging.getLogger(__name__)

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
        log_event(logger, logging.ERROR, "refund.failed", reason="user_not_found", order_no=order.order_no,
                  google_order_id=order.google_order_id, user_id=order.user_id)
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


async def _process_voided_token(
    purchase_token: str, package_name: str | None = None, google_order_id: str | None = None,
) -> Optional[dict]:
    """Revoke assets for a single voided purchase token. Returns a summary dict."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Order).where(Order.purchase_token == purchase_token).with_for_update()
            )
            order = result.scalar_one_or_none()
            if not order:
                log_event(logger, logging.WARNING, "refund.skipped", reason="order_not_found",
                          package_name=package_name, google_order_id=google_order_id)
                return None
            context = {"order_no": order.order_no, "user_id": order.user_id, "sku": order.sku,
                       "package_name": order.package_name, "google_order_id": order.google_order_id or google_order_id}
            if package_name is not None and order.package_name != package_name:
                log_event(logger, logging.WARNING, "refund.skipped", reason="package_mismatch", **context)
                return None
            if order.order_status not in (ORDER_STATUS_PAID, ORDER_STATUS_REFUNDED):
                log_event(logger, logging.INFO, "refund.skipped", reason="order_not_paid", order_status=order.order_status, **context)
                return None
            if google_order_id and order.google_order_id and google_order_id != order.google_order_id:
                log_event(logger, logging.WARNING, "refund.skipped", reason="google_order_id_mismatch", **context)
                return None

            backfill_google_id = bool(google_order_id and not order.google_order_id)
            if backfill_google_id:
                order.google_order_id = google_order_id
            if order.order_status == ORDER_STATUS_REFUNDED:
                if backfill_google_id:
                    # A later notification may supply the ID without changing the refund.
                    await db.commit()
                log_event(logger, logging.INFO, "refund.skipped", reason="already_refunded", **context)
                return None

            product = await get_product_for_order(db, order)
            if not product:
                log_event(logger, logging.ERROR, "refund.failed", reason="product_not_found", **context)
                raise RuntimeError(f"Refund product not found for order {order.order_no}")

            diamonds_revoked = await _revoke_order_assets(db, order, product)

            order.order_status = ORDER_STATUS_REFUNDED
            order.updated_time = int(time.time())
            db.add(order)
            display_order_no = order.google_order_id or order.order_no
            message = f"Your Google Play order {display_order_no} was refunded."
            if diamonds_revoked:
                unit = "diamond was" if diamonds_revoked == 1 else "diamonds were"
                message += f" {diamonds_revoked} {unit} deducted from your balance."
            await send_system_chat_message(db, order.user_id, message)
            detail = {
                "order_no": order.order_no, "user_id": order.user_id, "sku": order.sku,
                "diamonds_revoked": diamonds_revoked,
            }
            await db.commit()
            log_event(logger, logging.INFO, "refund.processed", diamonds_revoked=diamonds_revoked, **context)
            return detail
        except Exception:
            await db.rollback()
            raise


async def handle_voided_purchase_token(
    purchase_token: str, package_name: str | None = None, google_order_id: str | None = None,
) -> Optional[dict]:
    """Public entry: revoke assets for a voided (refunded) purchase token. Idempotent."""
    return await _process_voided_token(purchase_token, package_name, google_order_id)


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
        log_event(logger, logging.INFO, "refund.skipped", reason="no_paid_order", package_name=package_name, sku=sku)
        return None

    purchase = await google_play.verify_purchase(package_name, sku, purchase_token)
    if purchase.get("purchaseState") != google_play.PURCHASE_STATE_CANCELED:
        log_event(logger, logging.INFO, "refund.skipped", reason="cancellation_not_confirmed",
                  order_no=order_no, purchase_state=purchase.get("purchaseState"))
        return None
    return await _process_voided_token(purchase_token, package_name, google_play.get_purchase_order_id(purchase))


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
            log_event(logger, logging.ERROR, "refund.reconcile.failed", reason="collect_packages", exc_info=True)
            summary["errors"] += 1
            return summary

    for package_name in packages:
        summary["packages"] += 1
        page_token = None
        for _page in range(MAX_PAGES_PER_PACKAGE):
            try:
                resp = await google_play.list_voided_purchases(package_name, page_token=page_token)
            except GooglePlayError as e:
                log_event(logger, logging.ERROR, "refund.reconcile.failed", reason="list_voided_purchases",
                          package_name=package_name, google_status=e.status_code)
                summary["errors"] += 1
                break

            voided = resp.get("voidedPurchases") or []
            for item in voided:
                summary["voided_checked"] += 1
                purchase_token = item.get("purchaseToken")
                if not purchase_token or "voidedQuantity" in item:
                    continue
                try:
                    detail = await _process_voided_token(
                        purchase_token, package_name, google_play.get_purchase_order_id(item),
                    )
                except Exception:
                    log_event(logger, logging.ERROR, "refund.reconcile.failed", reason="process_purchase",
                              package_name=package_name, google_order_id=google_play.get_purchase_order_id(item), exc_info=True)
                    summary["errors"] += 1
                    continue
                if detail:
                    summary["refunded"] += 1
                    summary["details"].append(detail)

            page_token = (resp.get("tokenPagination") or {}).get("nextPageToken")
            if not page_token:
                break

    log_event(logger, logging.INFO, "refund.reconcile.finished", voided_checked=summary["voided_checked"],
              refunded=summary["refunded"], error_count=summary["errors"])
    return summary


