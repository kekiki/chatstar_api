import os
import unittest
from itertools import product
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ip_location import ip_location


class IPLocationTests(unittest.TestCase):
    def test_ipv4_and_ipv4_mapped_ipv6_use_the_ipv4_database(self):
        with patch.object(ip_location.q, "lookup", return_value=("Example", "Example ISP")) as lookup:
            for ip in ("192.0.2.10", "::ffff:192.0.2.10"):
                with self.subTest(ip=ip):
                    location = ip_location.get_ip_location(ip)
                    lookup.assert_called_with("192.0.2.10")
                    self.assertEqual(location.ip, ip)
                    self.assertEqual((location.country, location.isp), ("Example", "Example ISP"))
                    self.assertTrue(location.lookup_supported)


class GuestLoginIPLocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_env = {
            "ENV_MODE": "develop",
            "DATABASE_URL": "postgresql://test:test@127.0.0.1/test",
            "SECRET_KEY": "test-secret",
            **{key: "test" for key in (
                "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_ACCOUNT_ID", "R2_BUCKET_NAME",
                "R2_ENDPOINT", "R2_PUBLIC_DOMAIN",
            )},
        }
        with patch.dict(os.environ, test_env), patch("dotenv.load_dotenv"):
            from app.routers import auth
        cls.auth = auth

    def test_new_guest_can_log_in_when_geolocation_cannot_parse_the_address(self):
        addresses = (("2001:db8::42", "2001:db8::42"), ("invalid-ip", ""))
        for (ip, expected_ip), app_in_review in product(addresses, (False, True)):
            with self.subTest(ip=ip, app_in_review=app_in_review):
                db = Mock(spec=AsyncSession)
                existing_user = Mock()
                existing_user.scalars.return_value.first.return_value = None
                app_package = Mock()
                app_package.scalar_one_or_none.return_value = object()
                review_list = Mock()
                review_list.scalar_one_or_none.return_value = None
                app_review = Mock()
                app_review.scalar_one_or_none.return_value = object() if app_in_review else None
                counts = Mock()
                counts.one.return_value = SimpleNamespace(follow_count=0, fans_count=0, like_count=0)
                db.execute.side_effect = [
                    existing_user, app_package, review_list, review_list, review_list, app_review, counts,
                ]

                app = FastAPI()
                app.include_router(self.auth.router)
                app.dependency_overrides[self.auth.get_db] = lambda: db
                with TestClient(app) as client:
                    response = client.post("/api/auth/loginGuest", headers={
                        "device-id": "guest-test-device",
                        "package-name": "com.example.app",
                        "cf-connecting-ip": ip,
                        "user-agent": "ChatStar,1.0",
                    })

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["data"]["accessToken"])
                db.add.assert_called_once()
                user = db.add.call_args.args[0]
                self.assertIsInstance(user, self.auth.User)
                self.assertEqual(user.ip, expected_ip)
                self.assertEqual(user.is_review, app_in_review)
