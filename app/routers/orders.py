"""
Order routes: create order, query by orderNo, query by userId, verify Google purchase.
"""

import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app import google_play
from app.google_play import GooglePlayError
from app.database import get_db, get_db_readonly
from app.models import Order, User, Product
from app.models.order import ORDER_STATUS_PAID, ORDER_STATUS_FAILED
from app.models.transaction import ASSET_DIAMOND, ASSET_VIP, ASSET_CALL_CARD, ASSET_MATCH_CARD, ASSET_CHAT_CARD, TRANSACTION_PURCHASE
from app.schemas.orders import CreateOrderRequest, VerifyGoogleRequest
from app.security import current_user, current_user_readonly
from app.tools import add_transaction
from app.models.task import TYPE_RECHARGE_TIMES, TYPE_UNLOCK_VIP, TYPE_FIRST_RECHARGE

logger = logging.getLogger("orders")
router = APIRouter(prefix="/api", tags=["orders"])

@router.get("/order/products")
async def get_products(request: Request, db: AsyncSession = Depends(get_db_readonly)):
    """Get product list filtered by package_name from request header."""
    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package-name header")
    
    result = await db.execute(select(Product).where(Product.package_name == package_name).order_by(Product.diamonds, Product.vip_days))
    products = result.scalars().all()
    items = [product.to_dict() for product in products]
    return {"code": 200, "data": items}


@router.post("/order/create")
async def create_order(request: Request, data: CreateOrderRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Create a new order record."""
    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")
    
    now = datetime.now()
    transaction_no = f"cs-{now.year}-{now.month}-{now.day}-{now.hour}-{now.minute}-{now.second}-{now.microsecond}"
    order_no = f"O{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    agent = request.headers.get("user-agent")

    order = Order(
        package_name=package_name,
        user_id=user.user_id,
        transaction_no=transaction_no,
        order_no=order_no,
        sku=data.sku,
        type=data.type,
        pp_id=data.pp_id,
        anchor_id=data.anchor_id,
        path=data.path,
        order_status=0,
        agent=agent,
        created_time=int(time.time()),
    )
    db.add(order)
    await db.flush()
    return {"code": 200, "data": order.to_dict()}

@router.get("/user/orders")
async def get_user_orders(
    user: User = Depends(current_user_readonly),
    db: AsyncSession = Depends(get_db_readonly),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
):
    """Get paginated orders for the current user, sorted by created_time desc."""
    base_query = select(Order).where(Order.user_id == user.user_id)
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(Order.created_time.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    orders = result.scalars().all()
    items = [order.to_dict() for order in orders]
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.post("/order/verify")
async def verify_google_order(data: VerifyGoogleRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Verify a Google Play in-app purchase and update order status.

    Requires `GOOGLE_SERVICE_ACCOUNT_FILE` (recommended) or `GOOGLE_ACCESS_TOKEN`
    env var to be configured. Purchase tokens are bound to orders with a unique
    constraint so the same Google purchase can never be replayed on another order.
    """
    # 订单必须存在且属于当前用户
    result_order = await db.execute(select(Order).where(Order.order_no == data.order_no, Order.user_id == user.user_id))
    order = result_order.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 幂等保护：已验证成功的订单不重复发放奖励
    if order.order_status == ORDER_STATUS_PAID:
        return {"code": 200, "data": {"verified": True, "msg": "Order already verified"}}

    # 防重放：同一 Google 购买凭据只能绑定一个订单
    result_replay = await db.execute(
        select(Order.id).where(Order.purchase_token == data.purchase_token, Order.id != order.id)
    )
    if result_replay.scalar_one_or_none() is not None:
        logger.warning("purchase token replay rejected, order_no=%s user_id=%s", data.order_no, user.user_id)
        raise HTTPException(status_code=409, detail="Purchase token already used")

    # 订单 sku 必须与实际购买的商品一致，防止下单与发货脱钩
    if order.sku != data.product_id:
        logger.warning("sku mismatch rejected, order_no=%s order_sku=%s product_id=%s", data.order_no, order.sku, data.product_id)
        raise HTTPException(status_code=400, detail="Product does not match the order")

    # 商品必须属于对应包名
    result_product = await db.execute(
        select(Product).where(Product.sku == data.product_id, Product.package_name == data.package_name)
    )
    product = result_product.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 调 Google Play Developer API 验证购买
    try:
        result = await google_play.verify_purchase(data.package_name, data.product_id, data.purchase_token)
    except GooglePlayError as e:
        logger.error("google verify failed order_no=%s: %s", data.order_no, e)
        raise HTTPException(status_code=502, detail="Google purchase verification failed")

    purchase_state = result.get("purchaseState")
    now_ts = int(time.time())

    if purchase_state == google_play.PURCHASE_STATE_PURCHASED:
        order.order_status = ORDER_STATUS_PAID
        order.purchase_token = data.purchase_token
        order.google_order_id = result.get("orderId") or ""
        order.updated_time = now_ts
        db.add(order)
        
        from app.routers.tasks import add_task_progress
        task_type = TYPE_UNLOCK_VIP if order.isVip() else TYPE_RECHARGE_TIMES
        await add_task_progress(db, user.user_id, task_type, 1)
        if user.total == 0:
            await add_task_progress(db, user.user_id, TYPE_FIRST_RECHARGE, 1)
        
        user.balance = (user.balance or 0) + (product.diamonds or 0)
        if product.diamonds and product.diamonds > 0:
            await add_transaction(user, product.diamonds, asset_type=ASSET_DIAMOND, transaction_type=TRANSACTION_PURCHASE, db=db)
            user.total = (user.total or 0) + product.diamonds

        if product.vip_days and product.vip_days > 0:
            current_expire = user.vip_expire_time or now_ts
            base = max(current_expire, now_ts)
            user.vip_expire_time = base + product.vip_days * 86400
            await add_transaction(user, product.vip_days, asset_type=ASSET_VIP, transaction_type=TRANSACTION_PURCHASE, db=db)

        if product.call_card_num and product.call_card_num > 0:
            user.call_card_num = (user.call_card_num or 0) + product.call_card_num
            await add_transaction(user, product.call_card_num, asset_type=ASSET_CALL_CARD, transaction_type=TRANSACTION_PURCHASE, db=db)

        if product.match_card_num and product.match_card_num > 0:
            user.match_card_num = (user.match_card_num or 0) + product.match_card_num
            await add_transaction(user, product.match_card_num, asset_type=ASSET_MATCH_CARD, transaction_type=TRANSACTION_PURCHASE, db=db)

        if product.chat_card_num and product.chat_card_num > 0:
            user.chat_card_num = (user.chat_card_num or 0) + product.chat_card_num
            await add_transaction(user, product.chat_card_num, asset_type=ASSET_CHAT_CARD, transaction_type=TRANSACTION_PURCHASE, db=db)
        
        from app.tools import send_system_chat_message
        noti_msg = 'Congratulations! Your recharge was successful. '
        await send_system_chat_message(db,user.user_id,noti_msg)

        verified = True
    elif purchase_state == google_play.PURCHASE_STATE_CANCELED:
        order.order_status = ORDER_STATUS_FAILED
        order.updated_time = now_ts
        db.add(order)
        verified = False
    else:
        # PURCHASE_STATE_PENDING 或未知状态：保持待支付，不发货
        order.updated_time = now_ts
        db.add(order)
        verified = False

    return {"code": 200, "data": {"verified": verified, "google": result}}


@router.post("/order/processRefunds")
async def process_google_refunds(request: Request):
    """Manually trigger one Google refund processing pass.

    Requires the `x-cron-secret` header to match the `CRON_SECRET` env var
    (used by external cron / ops tooling). Disabled when CRON_SECRET is unset.
    """
    import os

    cron_secret = os.environ.get("CRON_SECRET")
    if not cron_secret:
        raise HTTPException(status_code=503, detail="Refund processing endpoint is disabled")
    if request.headers.get("x-cron-secret") != cron_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    from app.google_refund import process_refunds_once

    try:
        summary = await process_refunds_once()
    except Exception as e:
        logger.exception("manual refund processing failed")
        raise HTTPException(status_code=500, detail="Refund processing failed")
    return {"code": 200, "data": summary}
