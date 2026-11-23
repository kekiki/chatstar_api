"""
FastAPI application entry point.
Main application factory and configuration.
"""
import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles

from app import models
from app.config import ENV_MODE, HOST, PORT
from app.database import init_db_tables
from app.logging_config import RequestLoggingMiddleware, configure_logging, log_event, log_validation_error
from app.routers import auth, chat, orders, users, web, gifts, tasks, social, transactions, calls, rtdn


logger = logging.getLogger("app.lifecycle")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    configure_logging()
    log_event(logger, logging.INFO, "app.starting", environment=ENV_MODE)
    start = perf_counter()
    try:
        await init_db_tables()
    except Exception:
        log_event(logger, logging.ERROR, "app.startup_failed", reason="database_init", exc_info=True)
        raise
    log_event(logger, logging.INFO, "app.ready", duration_ms=round((perf_counter() - start) * 1000, 2))
    try:
        yield
    finally:
        log_event(logger, logging.INFO, "app.stopped")

api = FastAPI(
    title="ChatStar API",
    description="Chat and user management service",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    "https://chatstarapp.xyz",
    "https://www.chatstarapp.xyz",
]

api.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

api.add_exception_handler(RequestValidationError, log_validation_error)


# ===================== Health check endpoint =====================
@api.get("/")
async def home():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "chatstar-api",
        "version": "1.0.0",
    }

@api.get("/health")
async def health_check():
    return {"status": "ok"}

# # ===================== Mount files =====================
# # static 
# api.mount("/static", StaticFiles(directory="web"), name="static")
# api.mount("/delete_account", StaticFiles(directory="web/delete_account", html=True), name="delete_account_static")

# ===================== Register routers =====================
api.include_router(auth.router)
api.include_router(users.router)
api.include_router(web.router)
api.include_router(orders.router)
api.include_router(gifts.router)
api.include_router(tasks.router)
api.include_router(chat.router)
api.include_router(social.router)
api.include_router(transactions.router)
api.include_router(calls.router)
api.include_router(rtdn.router)

app = RequestLoggingMiddleware(api)

# ===================== Run application =====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=True,
        access_log=False,
        ws_ping_interval=20,
        ws_ping_timeout=60,
    )
