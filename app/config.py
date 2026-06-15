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

# Google OAuth settings
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Zoho OAuth
ZOHO_CLIENT_ID="1000.RW8LZJQGBY2US96JHPZOR6FGOVWJ3I"
ZOHO_CLIENT_SECRET="3c82827a433dc103187c68783bd358a922e5b5305e"
ZOHO_REFRESH_TOKEN="1000.766f24786cb412c6a9fc90dc0177a99f.6651f6c287c749b49cc432d8abbc3c7a"
ZOHO_ACCOUNT_URL="https://accounts.zoho.com"
ZOHO_ORG_ID="oqnetdde8d7c9c2c043348d5463c9c34a6dcd"
ZOHO_ROOT_FOLDER_ID="oqnetf79685ff6c1c487c8c2eb6b8fa5d4c23"