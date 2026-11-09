"""
FastAPI application entry point.
Main application factory and configuration.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles

from app import models
from app.config import HOST, PORT
from app.database import init_db_tables
from app.routers import auth, chat, orders, users, web, gifts, tasks, social, transactions, calls, rtdn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup, start background refund polling."""
    import asyncio

    await init_db_tables()
    from app.google_refund import start_refund_polling

    refund_task = start_refund_polling()
    yield
    if refund_task and not refund_task.done():
        refund_task.cancel()
        try:
            await refund_task
        except asyncio.CancelledError:
            pass

app = FastAPI(
    title="ChatStar API",
    description="Chat and user management service",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    "https://chatstarapp.xyz",
    "https://www.chatstarapp.xyz",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== Health check endpoint =====================
@app.get("/")
async def home():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "chatstar-api",
        "version": "1.0.0",
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# # ===================== Mount files =====================
# # static 
# app.mount("/static", StaticFiles(directory="web"), name="static")
# app.mount("/delete_account", StaticFiles(directory="web/delete_account", html=True), name="delete_account_static")

# ===================== Register routers =====================
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(web.router)
app.include_router(orders.router)
app.include_router(gifts.router)
app.include_router(tasks.router)
app.include_router(chat.router)
app.include_router(social.router)
app.include_router(transactions.router)
app.include_router(calls.router)
app.include_router(rtdn.router)

# ===================== Run application =====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=True,
        ws_ping_interval=20,
        ws_ping_timeout=60,
    )
