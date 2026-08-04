"""
User information routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models import User
from app.schemas import GoogleAttribution
from app.security import current_user, current_user_readonly, get_hash, verify_password

router = APIRouter(prefix="/api", tags=["users"])


class DeleteAccountWithAccountPasswordRequest(BaseModel):
    user_id: int
    password: str
class SetPasswordRequest(BaseModel):
    password: str

class UpdateFirebaseTokenRequest(BaseModel):
    firebase_token: str


@router.get("/user/info")
async def get_user_info(user: User = Depends(current_user_readonly)):
    """Get current user information."""
    return {"code": 200, "data": user.to_dict()}


@router.post("/user/googleAttribution")
async def set_user_attribution(
    attribution: GoogleAttribution,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set user attribution."""
    user.install_referrer = attribution.install_referrer
    user.referrer_click_timestamp_seconds = attribution.referrer_click_timestamp_seconds
    user.install_begin_timestamp_seconds = attribution.install_begin_timestamp_seconds
    user.referrer_click_timestamp_server_seconds = attribution.referrer_click_timestamp_server_seconds
    user.install_begin_timestamp_server_seconds = attribution.install_begin_timestamp_server_seconds
    user.install_version = attribution.install_version
    user.google_play_instant = attribution.google_play_instant
    return {"code": 200, "msg": "success"}


@router.post("/user/setPassword")
async def set_password(data: SetPasswordRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Set user password"""
    user.password = get_hash(data.password)
    return {"code": 200, "data": {"message": "Password set successfully"}}

@router.post("/user/deleteAccount")
async def delete_account(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Delete the current user's account."""
    await db.delete(user)
    return {"code": 200, "data": {"message": "Account deleted successfully"}}

@router.post("/user/deleteAccountWithAccountPassword")
async def delete_account_with_account_password(data: DeleteAccountWithAccountPasswordRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Delete the current user's account with account password."""
    if user.user_id != data.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    await db.delete(user)
    return {"code": 200, "data": {"message": "Account deleted successfully"}}

@router.post("/user/updateFirebaseToken")
async def update_firebase_token(data: UpdateFirebaseTokenRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Update user firebase token"""
    user.firebase_token = data.firebase_token
    return {"code": 200, "data": {"message": "update successfully"}}