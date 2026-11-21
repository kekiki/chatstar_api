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
from app.tools import add_transaction
from app.product_selection import get_product_for_order

logger = logging.getLogger("google_refund")

MAX_PAGES_PER_PACKAGE = 5


async def _collect_package_names(db: AsyncSession) -> list:
    """Package names to poll: online apps first, then any seen on orders."""
    packages = []
    result = await db.execute(select(AppList.package_name).where(AppList.is_online == True))  # noqa: E712
    packages.extend(result.scalars().all())
    result = await db.execute(select(Order.package_name).where(Order.package_name != None).distinct())  # noqa: E712
    packages.extend(result.scalars().all())
    return list(dict.fromkeys(p for p in packages if p))


async def _revoke_order_assets(db: AsyncSession, order: Order, product: Product) -> None:
    """Subtract the assets that were granted when this order was verified."""
    result = await db.execute(select(User).where(User.user_id == order.user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.error("refund: user %s not found for order %s", order.user_id, order.order_no)
        return

    now_ts = int(time.time())

    if product.diamonds and product.diamonds > 0:
        available = user.balance or 0
        revoked = min(available, product.diamonds)
        user.balance = available - revoked
        if revoked > 0:
            await add_transaction(user, -revoked, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_REFUND, db=db)

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


async def _process_voided_token(purchase_token: str) -> Optional[dict]:
    """Revoke assets for a single voided purchase token. Returns a summary dict."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Order).where(Order.purchase_token == purchase_token))
            order = result.scalar_one_or_none()
            if not order:
                return None
            if order.order_status != ORDER_STATUS_PAID:
                return None

            product = await get_product_for_order(db, order)
            if not product:
                logger.error(
                    "refund: product not found for refunded order %s (sku=%s pkg=%s), skipping revoke",
                    order.order_no, order.sku, order.package_name,
                )
                return None

            await _revoke_order_assets(db, order, product)

            order.order_status = ORDER_STATUS_REFUNDED
            order.updated_time = int(time.time())
            db.add(order)
            detail = {"order_no": order.order_no, "user_id": order.user_id, "sku": order.sku}
            await db.commit()
            logger.info("refund processed: order_no=%s user_id=%s", detail["order_no"], detail["user_id"])
            return detail
        except Exception:
            await db.rollback()
            raise


async def handle_voided_purchase_token(purchase_token: str) -> Optional[dict]:
    """Public entry: revoke assets for a voided (refunded) purchase token. Idempotent."""
    return await _process_voided_token(purchase_token)


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
                if not purchase_token:
                    continue
                try:
                    detail = await _process_voided_token(purchase_token)
                except Exception:
                    logger.exception("refund: failed to process voided token %s...", purchase_token[:32])
                    summary["errors"] += 1
                    continue
                if detail:
                    summary["refunded"] += 1
                    summary["details"].append(detail)

            page_token = (resp.get("pageInfo") or {}).get("nextPageToken")
            if not page_token:
                break

    return summary


