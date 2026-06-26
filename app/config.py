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

# Database Settings
DB_POOL_RECYCLE = 3600  # For PostgreSQL/MySQL

# Google OAuth settings
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Zoho OAuth
ZOHO_CLIENT_ID = os.environ.get("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN = os.environ.get("ZOHO_REFRESH_TOKEN", "")
ZOHO_ACCOUNT_URL = os.environ.get("ZOHO_ACCOUNT_URL", "")
ZOHO_ORG_ID = os.environ.get("ZOHO_ORG_ID", "")
ZOHO_ROOT_FOLDER_ID = os.environ.get("ZOHO_ROOT_FOLDER_ID", "")