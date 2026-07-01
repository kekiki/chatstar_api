"""
JWT and password authentication utilities.
"""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import ALGORITHM, SECRET_KEY, TOKEN_EXPIRE_DAYS
from app.database import get_db
from app.models import User

# ===================== JWT 认证 =====================
# Use pbkdf2_sha256 to avoid bcrypt backend compatibility issues on some Python environments.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hashed password."""
    return pwd_context.verify(plain, hashed)


def get_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_token(data: dict) -> str:
    """Create JWT token."""
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def current_user(
    authorization: str = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from token."""
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    
    # Support both "Bearer <token>" and "<token>" formats
    if authorization.startswith("Bearer "):
        token_str = authorization[7:]  # Remove "Bearer " prefix
    else:
        token_str = authorization  # Use the whole header as token
    
    try:
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid authorization")

        user = db.query(User).filter(User.user_id == int(user_id)).first()
        if not user:
            raise HTTPException(401, "User not found")
        
        return user
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {str(e)}")
