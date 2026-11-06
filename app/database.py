"""
Database configuration and session management.
"""
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import DATABASE_URL


def build_async_engine_url(database_url: str):
    """Convert a Postgres URL to asyncpg format and normalize SSL args."""
    if database_url.startswith("sqlite"):
        async_url = database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return async_url, {"check_same_thread": False}

    if database_url.startswith("postgresql://"):
        async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        async_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        async_url = database_url

    parsed = urlparse(async_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    connect_args = {}

    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = True
    elif sslmode == "disable":
        connect_args["ssl"] = False

    cleaned_url = urlunparse(parsed._replace(query=urlencode(query)))
    return cleaned_url, connect_args


ASYNC_DATABASE_URL, ASYNC_CONNECT_ARGS = build_async_engine_url(DATABASE_URL)

engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
}
if DATABASE_URL.startswith(("postgresql://", "postgres://")):
    engine_kwargs.update(
        {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_recycle": 300,
        }
    )

engine = create_async_engine(
    ASYNC_DATABASE_URL,
    connect_args=ASYNC_CONNECT_ARGS,
    **engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


def _upgrade_pay_orders(sync_conn) -> None:
    """Lightweight startup migration: add Google Play columns to existing tables.

    `create_all` does not alter existing tables, so add the purchase_token /
    google_order_id columns and their indexes manually (idempotent).
    """
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if not inspector.has_table("pay_orders"):
        return
    columns = {c["name"] for c in inspector.get_columns("pay_orders")}
    if "purchase_token" not in columns:
        sync_conn.execute(text("ALTER TABLE pay_orders ADD COLUMN purchase_token VARCHAR"))
    if "google_order_id" not in columns:
        sync_conn.execute(text("ALTER TABLE pay_orders ADD COLUMN google_order_id VARCHAR"))
    sync_conn.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_pay_orders_purchase_token ON pay_orders (purchase_token)")
    )
    sync_conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_pay_orders_google_order_id ON pay_orders (google_order_id)")
    )


async def init_db_tables():
    """Create database tables for all registered models and run schema upgrades."""
    import app.models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_upgrade_pay_orders)


async def get_db():
    """Dependency to get an async database session with transaction handling."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_readonly():
    """Dependency to get an async database session for read-only requests."""
    async with AsyncSessionLocal() as session:
        yield session
