"""
Application configuration module.
Handles environment variables and settings.
"""
import os

# ===================== 自动读取 Railway 环境变量 =====================
HOST: str = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get("PORT", '8000'))

# 数据库路径
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./../chatstar_data.db")

# JWT Settings
SECRET_KEY = os.environ.get("SECRET_KEY", "default-secret-key")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30