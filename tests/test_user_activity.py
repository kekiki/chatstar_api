import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def activity_api(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV_MODE", "develop")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    for key in ("R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_ACCOUNT_ID", "R2_BUCKET_NAME",
                "R2_ENDPOINT", "R2_PUBLIC_DOMAIN"):
        monkeypatch.setenv(key, "test")

    from app import activity, database
    from app.models import AppList, User
    from app.routers import auth, chat, tasks, users
    from app.security import create_token

    path = tmp_path / "activity.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}", pool_size=1, max_overflow=0, pool_timeout=0.2,
    )
    sessions = async_sessionmaker(engine, autoflush=False)
    for module in (activity, database, chat):
        monkeypatch.setattr(module, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(activity, "_tracked_date", None)
    monkeypatch.setattr(activity, "_tracked_users", set())
    monkeypatch.setattr(chat, "solicit_chat_task", AsyncMock())

    # 23:59 in Shanghai; advancing two minutes crosses its date boundary.
    clock = SimpleNamespace(now=datetime(2026, 1, 1, 15, 59, tzinfo=timezone.utc))
    monkeypatch.setattr(activity, "datetime", SimpleNamespace(now=lambda tz: clock.now.astimezone(tz)))

    @asynccontextmanager
    async def lifespan(_):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(database.Base.metadata.create_all)
            async with sessions.begin() as db:
                db.add_all([
                    AppList(package_name="com.example.activity"),
                    User(user_id=42, is_anchor=False, is_reward_received=True),
                    User(user_id=43, is_anchor=True, is_reward_received=True),
                ])
            yield
        finally:
            await engine.dispose()

    def query(sql, params=()):
        with closing(sqlite3.connect(path)) as conn:
            return conn.execute(sql, params).fetchall()

    def rows():
        return query("SELECT stat_date, user_id FROM daily_user_activity ORDER BY stat_date, user_id")

    def token(user_id):
        return create_token({"sub": str(user_id)})

    app = FastAPI(lifespan=lifespan)
    for router in (auth, chat, tasks, users):
        app.include_router(router.router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, activity=activity, clock=clock, query=query, rows=rows,
                              token=token, headers={"Authorization": f"Bearer {token(42)}"})


def test_read_only_request_records_activity_with_one_connection(activity_api):
    api = activity_api
    response = api.client.get("/api/user/tasks", headers=api.headers)
    assert response.status_code == 200
    assert api.rows() == [("2026-01-01", 42)]

    # A worker without a local cache must still deduplicate at the database.
    api.activity._tracked_users.clear()
    assert api.client.get("/api/user/info", headers=api.headers).status_code == 200
    assert api.rows() == [("2026-01-01", 42)]


def test_write_request_commits_before_recording_activity(activity_api, monkeypatch):
    api = activity_api
    record = api.activity.record_user_activity

    async def check_commit_then_record(stat_date, user_id):
        assert api.query("SELECT firebase_token FROM app_users WHERE user_id = ?", (user_id,)) == [("new-token",)]
        await record(stat_date, user_id)

    monkeypatch.setattr(api.activity, "record_user_activity", check_commit_then_record)
    response = api.client.post("/api/user/updateFirebaseToken", headers=api.headers,
                               json={"firebase_token": "new-token"})
    assert response.status_code == 200
    assert api.rows() == [("2026-01-01", 42)]


def test_new_guest_login_records_activity_with_one_connection(activity_api):
    api = activity_api
    response = api.client.post("/api/auth/loginGuest", headers={
        "device-id": "activity-test-device",
        "package-name": "com.example.activity",
        "cf-connecting-ip": "2001:db8::42",
        "user-agent": "ChatStar,1.0",
    })
    assert response.status_code == 200
    user_id = response.json()["data"]["user"]["user_id"]
    assert api.rows() == [("2026-01-01", user_id)]


def test_websocket_connect_and_cross_midnight_message_record_activity(activity_api, monkeypatch):
    api = activity_api
    recorded = Event()
    record = api.activity.record_user_activity

    async def record_then_signal(stat_date, user_id):
        await record(stat_date, user_id)
        recorded.set()

    monkeypatch.setattr(api.activity, "record_user_activity", record_then_signal)
    with api.client.websocket_connect(f"/api/ws/connect?token={api.token(42)}") as ws:
        assert recorded.wait(timeout=2), "authenticated handshake did not record activity"
        assert api.rows() == [("2026-01-01", 42)]

        api.clock.now += timedelta(minutes=2)
        ws.send_json({"action": "ping"})
        ws.receive_json()

    assert api.rows() == [("2026-01-01", 42), ("2026-01-02", 42)]


def test_websocket_does_not_count_anchors_or_invalid_tokens(activity_api):
    api = activity_api
    with api.client.websocket_connect(f"/api/ws/connect?token={api.token(43)}") as ws:
        ws.send_json({"action": "ping"})
        ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with api.client.websocket_connect("/api/ws/connect?token=invalid"):
            pytest.fail("WebSocket accepted an invalid token")
    assert api.rows() == []
