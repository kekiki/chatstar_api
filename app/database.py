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
}
if DATABASE_URL.startswith(("postgresql://", "postgres://")):
    engine_kwargs.update(
        {
            "pool_size": 3,
            "max_overflow": 8,
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


async def init_db_tables():
    """Create database tables for all registered models."""
    import app.models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency to get an async database session with transaction handling."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_readonly():
    """Dependency to get an async database session for read-only requests."""
    async with AsyncSessionLocal() as session:
        yield session
