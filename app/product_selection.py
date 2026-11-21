"""Product lookup helpers shared by purchase and refund flows."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

logger = logging.getLogger("product_selection")


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
        logger.warning(
            "multiple product rows matched order; using newest row "
            "order_no=%s sku=%s package_name=%s type=%s ids=%s",
            order.order_no,
            order.sku,
            order.package_name,
            order.type,
            [product.id for product in products],
        )
    return products[0]
