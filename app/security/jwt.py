"""
JWT and password authentication utilities.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ALGORITHM, SECRET_KEY, TOKEN_EXPIRE_DAYS
from app.database import get_db, get_db_readonly
from app.models import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt", "sha256_crypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except UnknownHashError:
        return False


def get_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return authorization


async def _resolve_user(authorization: Optional[str], db: AsyncSession) -> User:
    token_str = _extract_token(authorization)
    try:
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid authorization")

        result = await db.execute(select(User).where(User.user_id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(401, "User not found")

        return user
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {str(e)}")


async def current_user(
    authorization: str = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _resolve_user(authorization, db)


async def current_user_readonly(
    authorization: str = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db_readonly),
) -> User:
    return await _resolve_user(authorization, db)
