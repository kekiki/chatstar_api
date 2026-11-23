import os
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
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
            from app.routers import orders

        cls.orders = orders

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
        self.add_transaction.assert_not_awaited()

    def test_matching_profile_id_fulfills_order_without_client_sku(self):
        self.set_google_purchase(obfuscatedExternalProfileId=self.order.transaction_no)

        response = self.verify_order()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["verified"])
        self.assertEqual(self.user.balance, 110)
        self.assertEqual(self.order.order_status, self.orders.ORDER_STATUS_PAID)
        self.assertEqual(self.order.purchase_token, "test-token")
        self.lookup_product.assert_awaited_once_with(self.db, self.order)
        self.verify.assert_awaited_once_with(self.order.package_name, self.order.sku, "test-token")

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
