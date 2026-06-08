"""
Authentication routes: register and login.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import create_token, get_hash, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register")
def register(request: Request, db: Session = Depends(get_db)):
    """Register a new user with device_id from request header."""
    device_id = request.headers.get("device-id") or request.headers.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="缺少 device_id 请求头")

    if db.query(User).filter(User.device_id == device_id).first():
        raise HTTPException(400, "设备已注册")
    
    password = str(uuid.uuid4())[:8]
    hashed = get_hash(password)

    # Create user, let DB assign primary key `id`
    user = User(hashed_password=hashed, device_id=device_id)
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "code": 200,
        "data": {"user_id": user.id, "password": password}
    }


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login with user_id and password."""
    try:
        uid = int(form_data.username)
    except Exception:
        raise HTTPException(status_code=401, detail="账号或密码错误")

    user = db.query(User).filter(User.id == uid).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "账号或密码错误")
    
    token = create_token({"sub": user.id})
    return {
        "code": 200,
        "data": {"access_token": token, "token_type": "bearer"}
    }
