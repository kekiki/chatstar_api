"""
JWT and password authentication utilities.
"""
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import ALGORITHM, SECRET_KEY, TOKEN_EXPIRE_DAYS
from app.database import get_db
from app.models import User

# ===================== JWT 认证 =====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hashed password."""
    return pwd_context.verify(plain, hashed)


def get_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_token(data: dict) -> str:
    """Create JWT token."""
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "无效授权")
        try:
            uid = int(user_id)
        except Exception:
            raise HTTPException(401, "无效授权")

        user = db.query(User).filter(User.id == uid).first()
        if not user:
            raise HTTPException(401, "用户不存在")
        return user
    except JWTError:
        raise HTTPException(401, "令牌失效")
