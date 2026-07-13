"""
FastAPI application entry point.
Main application factory and configuration.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import models
from app.config import HOST, PORT
from app.database import init_db_tables
from app.routers import anchor, auth, orders, users, web


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    await init_db_tables()
    yield

app = FastAPI(
    title="ChatStar API",
    description="Chat and user management service",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产替换为你的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== Mount static files =====================
if os.path.exists("web"):
    app.mount("/static", StaticFiles(directory="web"), name="static")

# ===================== Register routers =====================
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(web.router)
app.include_router(orders.router)
app.include_router(anchor.router)

# ===================== Health check endpoint =====================
@app.get("/")
async def home():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "chatstar-api",
        "version": "1.0.0",
    }


# ===================== Run application =====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
