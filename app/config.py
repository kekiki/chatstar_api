"""
Application configuration module.
Handles environment variables and settings.
"""
import os

# ===================== 自动读取 Railway 环境变量 =====================
PORT = int(os.environ.get("PORT", 8080))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "default-secret-key")

# JWT Settings
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

# Database Settings
DB_CHECK_SAME_THREAD = True  # For SQLite only
DB_POOL_RECYCLE = 3600  # For PostgreSQL/MySQL
