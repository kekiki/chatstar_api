"""
FastAPI application entry point.
Main application factory and configuration.
"""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import PORT
from app.database import Base, engine
from app import models
from app.routers import auth, users, web, files, orders, anchor


# ===================== Create database tables =====================
Base.metadata.create_all(bind=engine)

# ===================== Application factory =====================
app = FastAPI(
    title="ChatStar API",
    description="Chat and user management service",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 生产替换为你的前端域名
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
app.include_router(files.router)
app.include_router(orders.router)
app.include_router(anchor.router)

# ===================== Health check endpoint =====================
@app.get("/")
def home():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "chatstar-api",
        "version": "1.0.0"
    }


# ===================== Run application =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
