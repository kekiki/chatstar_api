"""Product lookup helpers shared by purchase and refund flows."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import log_event
from app.models.product import Product

logger = logging.getLogger(__name__)


async def get_product_for_order(db: AsyncSession, order) -> Product | None:
    """Find the product configuration that belongs to an order.

    SKU is not globally unique: normal, first-recharge, and VIP products can
    share an SKU in the existing data. The order type is therefore part of the
    lookup. Keep the newest row as a deterministic fallback for legacy data
    that contains duplicate rows with the same type.
    """
    result = await db.execute(
        select(Product)
        .where(
            Product.sku == order.sku,
            Product.package_name == order.package_name,
            Product.type == order.type,
        )
        .order_by(Product.id.desc())
        .limit(2)
    )
    products = result.scalars().all()
    if not products:
        return None

    if len(products) > 1:
        log_event(logger, logging.WARNING, "product.duplicate_match", order_no=order.order_no,
                  sku=order.sku, package_name=order.package_name, product_id=products[0].id)
    return products[0]
