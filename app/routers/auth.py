"""
Authentication routes: register and login.
"""
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import create_token, get_hash, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/loginGuest")
def login_guest(request: Request, db: Session = Depends(get_db)):
    """Login as a guest user with device_id from request header."""
    device_id = request.headers.get("device-id") or request.headers.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    user = db.query(User).filter(User.device_id == device_id).first()
    if user:
        token = create_token({"sub": user.id})
        return {
            "code": 200,
            "data": {"access_token": token, "user_id": user.id}
        }
    
    timeinterval = time.time()
    # Create user, let DB assign primary key `id`
    user = User(device_id=device_id, created_at=int(timeinterval))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token({"sub": user.id})
    return {
        "code": 200,
        "data": {"access_token": token, "user_id": user.id}
    }


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login with user_id and password."""
    try:
        uid = int(form_data.username)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user = db.query(User).filter(User.id == uid).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Invalid username or password")
    
    token = create_token({"sub": user.id})
    return {
        "code": 200,
        "data": {"access_token": token, "user_id": user.id}
    }
