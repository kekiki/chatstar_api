"""
Application configuration module.
Handles environment variables and settings.
"""
import os

# ===================== 自动读取 Railway 环境变量 =====================
PORT = int(os.environ.get("PORT", 8080))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./chatstar_data.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "default-secret-key")

# JWT Settings
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30