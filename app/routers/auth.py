"""
Authentication routes: register and login.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import GOOGLE_CLIENT_ID
from app.database import get_db
from app.models import User, AppList
from app.security import create_token
from app.schemas import GoogleLoginRequest

router = APIRouter(prefix="/api", tags=["auth"])



def verify_google_id_token(id_token: str) -> dict:
    """Verify a Google ID token using Google's tokeninfo endpoint."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")

    token_info_url = (
        "https://oauth2.googleapis.com/tokeninfo?id_token="
        + urllib.parse.quote(id_token)
    )

    try:
        with urllib.request.urlopen(token_info_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        raise HTTPException(status_code=401, detail="Invalid Google ID token")
    except Exception:
        raise HTTPException(status_code=401, detail="Unable to verify Google token")

    if payload.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Google token audience mismatch")

    verified = str(payload.get("email_verified", "false")).lower() == "true"
    if not verified:
        raise HTTPException(status_code=401, detail="Google email is not verified")

    return payload


@router.post("/loginGoogle")
def login_google(data: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Login or register a user using a Google ID token."""
    payload = verify_google_id_token(data.id_token)
    google_id = payload.get("sub")
    if not google_id:
        raise HTTPException(status_code=401, detail="Invalid Google token payload")

    email = payload.get("email")
    nickname = payload.get("name")
    avatar = payload.get("picture")

    user = db.query(User).filter(User.google_id == google_id).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()

    if user:
        if not user.google_id:
            user.google_id = google_id
        if email and not user.email:
            user.email = email
        if nickname:
            user.nickname = nickname
        if avatar:
            user.avatar = avatar
    else:
        user = User(
            google_id=google_id,
            email=email,
            nickname=nickname,
            avatar=avatar,
            created_time=int(time.time())
        )
        db.add(user)

    db.commit()
    db.refresh(user)

    token = create_token({"sub": user.id})
    return {
        "code": 200,
        "data": {"accessToken": token}
    }


@router.post("/loginGuest")
def login_guest(request: Request, db: Session = Depends(get_db)):
    """Login as a guest user with device_id from request header."""
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")

    package = db.query(AppList).filter(AppList.package_name == package_name).first()
    if not package:
        raise HTTPException(status_code=400, detail="Invalid package_name")

    user = db.query(User).filter(User.device_id == device_id).first()
    if user:
        token = create_token({"sub": user.id})
        return {
            "code": 200,
            "data": {"accessToken": token}
        }
    
    # Create user, let DB assign primary key `id`
    user = User(device_id=device_id, app_id=package.id)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token({"sub": user.id})
    return {
        "code": 200,
        "data": {"accessToken": token}
    }


# @router.post("/loginPassword")
# def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
#     """Login with user_id and password."""
#     try:
#         uid = int(form_data.username)
#     except Exception:
#         raise HTTPException(status_code=401, detail="Invalid username or password")

#     user = db.query(User).filter(User.id == uid).first()
#     if not user or not verify_password(form_data.password, user.hashed_password):
#         raise HTTPException(401, "Invalid username or password")
    
#     token = create_token({"sub": user.id})
#     return {
#         "code": 200,
#         "data": {"accessToken": token}
#     }
