import asyncio
import base64
import json
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


class GoogleOrderVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {
            "ENV_MODE": "develop",
            "DATABASE_URL": "postgresql://test:test@127.0.0.1/test",
            **{key: "test" for key in (
                "SECRET_KEY", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_ACCOUNT_ID",
                "R2_BUCKET_NAME", "R2_ENDPOINT", "R2_PUBLIC_DOMAIN",
            )},
        }
        with patch.dict(os.environ, env), patch("dotenv.load_dotenv"):
            from app.routers import orders, rtdn

        cls.orders = orders
        cls.rtdn = rtdn

    def setUp(self):
        orders = self.orders
        self.order = orders.Order(
            id=1, user_id=42, order_no="order-1", transaction_no="transaction-1",
            package_name="com.example.app", sku="diamond-pack", type=1,
            order_status=0, created_time=100, updated_time=100,
        )
        self.user = orders.User(user_id=42, balance=10, total=10)
        self.product = orders.Product(sku=self.order.sku, type=1, diamonds=100)
        self.db = Mock(spec=AsyncSession)
        self.order_result = Mock()
        self.order_result.scalar_one_or_none.return_value = self.order
        token_result = Mock()
        token_result.scalar_one_or_none.return_value = None
        self.db.execute.side_effect = [self.order_result, token_result]

        api = FastAPI()
        api.include_router(orders.router)
        api.include_router(self.rtdn.router)
        api.dependency_overrides[orders.get_db] = lambda: self.db
        api.dependency_overrides[orders.current_user] = lambda: self.user
        self.client = TestClient(api)
        self.addCleanup(self.client.close)

        self.verify = self.enterContext(patch.object(orders.google_play, "verify_purchase"))
        self.lookup_product = self.enterContext(
            patch.object(orders, "get_product_for_order", return_value=self.product)
        )
        self.add_transaction = self.enterContext(patch.object(orders, "add_transaction"))
        self.enterContext(patch("app.routers.tasks.add_task_progress"))
        self.enterContext(patch("app.tools.send_system_chat_message"))
        self.enterContext(patch.dict(os.environ, {"GOOGLE_PLAY_LEGACY_PROFILE_ID_CUTOFF": ""}))

    def verify_order(self, token="test-token", **payload):
        return self.client.post(
            "/api/order/verify",
            json={"transactionNo": self.order.transaction_no, "purchaseToken": token, **payload},
            headers={"package-name": self.order.package_name},
        )

    def set_google_purchase(self, **purchase):
        self.verify.return_value = {"purchaseState": 0, "orderId": "GPA.test", **purchase}

    def assert_not_fulfilled(self):
        self.assertEqual(self.user.balance, 10)
        self.assertEqual(self.order.order_status, 0)
        self.assertIsNone(self.order.purchase_token)
        self.assertIsNone(self.order.google_granted_diamonds)
        self.add_transaction.assert_not_awaited()

    def test_matching_profile_id_fulfills_order_without_client_sku(self):
        self.set_google_purchase(obfuscatedExternalProfileId=self.order.transaction_no)

        response = self.verify_order()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["verified"])
        self.assertEqual(self.user.balance, 110)
        self.assertEqual(self.order.order_status, self.orders.ORDER_STATUS_PAID)
        self.assertEqual(self.order.purchase_token, "test-token")
        self.assertEqual(self.order.google_granted_diamonds, 100)
        self.lookup_product.assert_awaited_once_with(self.db, self.order)
        self.verify.assert_awaited_once_with(self.order.package_name, self.order.sku, "test-token")

    def test_bonus_only_product_writes_diamond_transaction(self):
        self.product.diamonds = 0
        self.product.reward_diamonds = 25
        self.set_google_purchase(obfuscatedExternalProfileId=self.order.transaction_no)

        response = self.verify_order()

        self.assertTrue(response.json()["data"]["verified"])
        self.assertEqual(self.user.balance, 35)
        self.assertEqual(self.user.total, 35)
        self.assertEqual(self.order.google_granted_diamonds, 25)
        self.add_transaction.assert_awaited_once_with(
            self.user, 25, asset_type=self.orders.ASSET_DIAMOND,
            transaction_type=self.orders.TRANSACTION_PURCHASE, db=self.db,
        )

    def test_purchase_and_refund_use_same_amount_including_bonus(self):
        from app import google_refund

        self.product.reward_diamonds = 25
        self.set_google_purchase(obfuscatedExternalProfileId=self.order.transaction_no)
        response = self.verify_order()

        self.assertTrue(response.json()["data"]["verified"])
        self.assertEqual(self.user.balance, 135)
        self.assertEqual(self.user.total, 135)
        self.assertEqual(self.order.google_granted_diamonds, 125)
        self.add_transaction.assert_awaited_once_with(
            self.user, 125, asset_type=self.orders.ASSET_DIAMOND,
            transaction_type=self.orders.TRANSACTION_PURCHASE, db=self.db,
        )

        self.product.diamonds = 90
        self.product.reward_diamonds = 120
        refund_db = Mock(spec=AsyncSession)
        user_result = Mock()
        user_result.scalar_one_or_none.return_value = self.user
        refund_db.execute.side_effect = [self.order_result, user_result, self.order_result]
        session = MagicMock()
        session.__aenter__.return_value = refund_db

        async def refund_twice():
            detail = await google_refund.handle_voided_purchase_token("test-token")
            self.assertEqual(detail["order_no"], self.order.order_no)
            self.assertIsNone(await google_refund.handle_voided_purchase_token("test-token"))

        with (
            patch.object(google_refund, "AsyncSessionLocal", return_value=session),
            patch.object(google_refund, "get_product_for_order", return_value=self.product),
            patch.object(google_refund, "add_transaction") as refund_transaction,
            patch.object(google_refund, "send_system_chat_message") as refund_message,
        ):
            asyncio.run(refund_twice())

        self.assertEqual(self.user.balance, 10)
        self.assertEqual(self.order.order_status, google_refund.ORDER_STATUS_REFUNDED)
        refund_db.commit.assert_awaited_once()
        refund_transaction.assert_awaited_once_with(
            self.user, -125, asset_type=google_refund.ASSET_DIAMOND,
            transaction_type=google_refund.TRANSACTION_REFUND, db=refund_db,
        )
        refund_message.assert_awaited_once_with(
            refund_db, self.user.user_id,
            "Your Google Play order order-1 was refunded. 125 diamonds were deducted from your balance.",
        )

        self.db.execute.side_effect = [self.order_result]
        self.assertEqual(self.verify_order().status_code, 409)
        self.assertEqual(self.user.balance, 10)
        self.add_transaction.assert_awaited_once()

    def test_refund_respects_legacy_orders_zero_grants_and_available_balance(self):
        from app import google_refund

        self.product.reward_diamonds = 25
        user_result = Mock()
        user_result.scalar_one_or_none.return_value = self.user
        self.db.execute.side_effect = None
        self.db.execute.return_value = user_result

        for grant, balance, deduction in [(None, 150, 100), (0, 150, 0), (125, 20, 20)]:
            with self.subTest(grant=grant, balance=balance):
                self.order.google_granted_diamonds = grant
                self.user.balance = balance
                with patch.object(google_refund, "add_transaction") as refund_transaction:
                    asyncio.run(google_refund._revoke_order_assets(self.db, self.order, self.product))
                self.assertEqual(self.user.balance, balance - deduction)
                if deduction:
                    refund_transaction.assert_awaited_once_with(
                        self.user, -deduction, asset_type=google_refund.ASSET_DIAMOND,
                        transaction_type=google_refund.TRANSACTION_REFUND, db=self.db,
                    )
                else:
                    refund_transaction.assert_not_awaited()

    def test_migration_leaves_existing_diamond_grant_null(self):
        from app.database import _upgrade_pay_orders

        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE pay_orders (id INTEGER PRIMARY KEY, purchase_token VARCHAR, google_order_id VARCHAR)"))
            conn.execute(text("INSERT INTO pay_orders (id) VALUES (1)"))
            _upgrade_pay_orders(conn)
            _upgrade_pay_orders(conn)

            columns = {column["name"]: column for column in inspect(conn).get_columns("pay_orders")}
            self.assertTrue(columns["google_granted_diamonds"]["nullable"])
            self.assertEqual(conn.execute(text("SELECT google_granted_diamonds FROM pay_orders")).one(), (None,))

    def send_rtdn(self, event, *, wrapped=True, secret="test-secret"):
        payload = {"packageName": self.order.package_name, **event}
        if wrapped:
            payload = {"message": {"data": base64.b64encode(json.dumps(payload).encode()).decode()}}
        with patch.dict(os.environ, {"RTDN_SECRET": "test-secret"}):
            return self.client.post("/api/google/rtdn", json=payload, headers={"x-rtdn-secret": secret})

    def test_rtdn_accepts_full_refunds_in_wrapped_and_unwrapped_pushes(self):
        with patch.object(self.rtdn, "handle_voided_purchase_token") as process:
            for wrapped in (True, False):
                with self.subTest(wrapped=wrapped):
                    process.reset_mock()
                    event = {"voidedPurchaseNotification": {"purchaseToken": "test-token", "refundType": 1}}
                    self.assertEqual(self.send_rtdn(event, wrapped=wrapped).status_code, 200)
                    process.assert_awaited_once_with("test-token", self.order.package_name)

    def test_rtdn_does_not_revoke_partial_or_invalid_refunds(self):
        with patch.object(self.rtdn, "handle_voided_purchase_token") as process:
            for refund_type in (2, None, True):
                event = {"voidedPurchaseNotification": {"purchaseToken": "test-token", "refundType": refund_type}}
                self.assertEqual(self.send_rtdn(event).status_code, 200)
            self.assertEqual(self.send_rtdn({"voidedPurchaseNotification": {"purchaseToken": "test-token", "refundType": 1}}, secret="bad-secret").status_code, 403)
            process.assert_not_awaited()

    def test_rtdn_routes_one_time_cancellation_and_retries_google_errors(self):
        event = {"oneTimeProductNotification": {"notificationType": 2, "purchaseToken": "test-token", "sku": self.order.sku}}
        with patch.object(self.rtdn, "handle_canceled_one_time_purchase") as process:
            self.assertEqual(self.send_rtdn(event).status_code, 200)
            process.assert_awaited_once_with("test-token", self.order.package_name, self.order.sku)
            process.side_effect = self.orders.GooglePlayError("temporary failure")
            self.assertEqual(self.send_rtdn(event).status_code, 502)

    def test_one_time_cancellation_must_match_paid_order_and_google_state(self):
        from app import google_refund

        order_no_result = Mock()
        self.db.execute.side_effect = None
        self.db.execute.return_value = order_no_result
        session = MagicMock()
        session.__aenter__.return_value = self.db
        args = ("test-token", self.order.package_name, self.order.sku)
        with (
            patch.object(google_refund, "AsyncSessionLocal", return_value=session),
            patch.object(google_refund, "_process_voided_token") as process,
        ):
            order_no_result.scalar_one_or_none.return_value = None
            self.assertIsNone(asyncio.run(google_refund.handle_canceled_one_time_purchase(*args)))
            self.verify.assert_not_awaited()

            order_no_result.scalar_one_or_none.return_value = self.order.order_no
            self.set_google_purchase()
            self.assertIsNone(asyncio.run(google_refund.handle_canceled_one_time_purchase(*args)))
            self.verify.assert_awaited_once_with(self.order.package_name, self.order.sku, "test-token")
            process.assert_not_awaited()

            self.set_google_purchase(purchaseState=google_refund.google_play.PURCHASE_STATE_CANCELED)
            asyncio.run(google_refund.handle_canceled_one_time_purchase(*args))
            process.assert_awaited_once_with("test-token", self.order.package_name)

    def test_manual_scan_follows_google_pagination_and_ignores_partial_refunds(self):
        from app import google_refund

        session = MagicMock()
        session.__aenter__.return_value = self.db
        pages = [
            {"tokenPagination": {"nextPageToken": "next"},
             "voidedPurchases": [{"purchaseToken": "partial-token", "voidedQuantity": 1}]},
            {"voidedPurchases": [{"purchaseToken": "full-token"}]},
        ]
        with (
            patch.object(google_refund, "AsyncSessionLocal", return_value=session),
            patch.object(google_refund, "_collect_package_names", return_value=[self.order.package_name]),
            patch.object(google_refund.google_play, "list_voided_purchases", side_effect=pages) as query,
            patch.object(google_refund, "_process_voided_token", return_value={"order_no": "order-1"}) as process,
        ):
            result = asyncio.run(google_refund.process_refunds_once())
        self.assertEqual(result["voided_checked"], 2)
        self.assertEqual(result["refunded"], 1)
        process.assert_awaited_once_with("full-token", self.order.package_name)
        self.assertEqual(query.await_args.kwargs, {"page_token": "next"})

    def test_manual_revoke_requires_an_exact_fully_refunded_google_order(self):
        from app import google_refund

        self.order.order_status = self.orders.ORDER_STATUS_PAID
        self.order.google_order_id = "GPA.test"
        self.order.purchase_token = "test-token"
        self.db.execute.side_effect = None
        self.db.execute.return_value = self.order_result
        session = MagicMock()
        session.__aenter__.return_value = self.db
        confirmed = {"state": "REFUNDED", "orderId": "GPA.test", "purchaseToken": "test-token"}
        with (
            patch.object(google_refund, "AsyncSessionLocal", return_value=session),
            patch.object(google_refund.google_play, "get_order") as get_order,
            patch.object(google_refund, "_process_voided_token") as process,
        ):
            for override in ({"state": "PARTIALLY_REFUNDED"}, {"orderId": "wrong"}, {"purchaseToken": "wrong"}):
                get_order.return_value = confirmed | override
                self.assertIsNone(asyncio.run(google_refund.reconcile_refunded_order(self.order.order_no)))
            process.assert_not_awaited()

            get_order.return_value = confirmed
            asyncio.run(google_refund.reconcile_refunded_order(self.order.order_no))
            self.assertEqual(get_order.await_args.args, (self.order.package_name, self.order.google_order_id))
            process.assert_awaited_once_with(self.order.purchase_token, self.order.package_name)

    def test_mismatched_profile_id_never_fulfills_even_with_legacy_cutoff(self):
        self.set_google_purchase(obfuscatedExternalProfileId="other-order", purchaseTimeMillis="101000")
        with patch.dict(os.environ, {"GOOGLE_PLAY_LEGACY_PROFILE_ID_CUTOFF": "200"}):
            response = self.verify_order(jsonPurchaseInfo='{"obfuscatedProfileId":"transaction-1"}')

        self.assertEqual(response.status_code, 400)
        self.assert_not_fulfilled()
        self.db.add.assert_not_called()

    def test_missing_profile_id_rejected_by_default(self):
        self.set_google_purchase(purchaseTimeMillis="101000")

        self.assertEqual(self.verify_order().status_code, 400)
        self.assert_not_fulfilled()
        self.db.add.assert_not_called()

    def test_missing_profile_id_accepted_only_before_explicit_cutoff(self):
        self.set_google_purchase(purchaseTimeMillis="199999")
        with patch.dict(os.environ, {"GOOGLE_PLAY_LEGACY_PROFILE_ID_CUTOFF": "200"}):
            response = self.verify_order()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["verified"])
        self.assertEqual(self.user.balance, 110)

    def test_google_purchase_at_cutoff_is_not_legacy(self):
        self.set_google_purchase(purchaseTimeMillis="200000")
        with patch.dict(os.environ, {"GOOGLE_PLAY_LEGACY_PROFILE_ID_CUTOFF": "200"}):
            self.assertEqual(self.verify_order().status_code, 400)
        self.assert_not_fulfilled()

    def test_order_created_at_cutoff_is_not_legacy(self):
        self.order.created_time = 200
        self.set_google_purchase(purchaseTimeMillis="199999")
        with patch.dict(os.environ, {"GOOGLE_PLAY_LEGACY_PROFILE_ID_CUTOFF": "200"}):
            self.assertEqual(self.verify_order().status_code, 400)
        self.assert_not_fulfilled()

    def test_pending_purchase_without_profile_id_does_not_fulfill(self):
        self.set_google_purchase(purchaseState=self.orders.google_play.PURCHASE_STATE_PENDING)

        response = self.verify_order()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["verified"])
        self.assert_not_fulfilled()

    def test_paid_order_only_returns_verified_for_the_original_token(self):
        self.order.order_status = self.orders.ORDER_STATUS_PAID
        self.order.purchase_token = "original-token"
        self.db.execute.side_effect = [self.order_result, self.order_result]

        self.assertEqual(self.verify_order(token="different-token").status_code, 409)
        response = self.verify_order(token="original-token")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["verified"])
        self.assertEqual(self.user.balance, 10)
        self.verify.assert_not_awaited()
        self.add_transaction.assert_not_awaited()
