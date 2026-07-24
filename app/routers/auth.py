"""
Authentication routes: register and login.
"""

import asyncio
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ip_location import IPLocationResult, ip_location
from app.models import AppList, AppReview, BlackWhiteDevice, BlackWhiteIp, BlackWhiteUser, User, UserFollow, UserLike
from app.schemas import GoogleUserInfo, UserAgent
from app.security import create_token, current_user, get_hash, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


class PasswordLoginRequest(BaseModel):
    user_id: int
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class SetPasswordRequest(BaseModel):
    password: str


def _get_client_real_ip(request: Request) -> str:
    """适配 Railway / Cloudflare / 通用代理 获取真实访客IP"""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    xff = request.headers.get("x-forwarded-for")
    if xff:
        first_ip = xff.split(",")[0].strip()
        return first_ip

    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()

    return request.client.host


async def _check_review_user(db: AsyncSession, user_id: int, device_id: str, agent: str, ip_info: IPLocationResult) -> bool:
    """Check whether the user should be marked for review."""
    result = await db.execute(select(BlackWhiteUser).where(BlackWhiteUser.user_id == user_id))
    black_white_user = result.scalar_one_or_none()
    if black_white_user and black_white_user.status == 0:
        return True

    result = await db.execute(select(BlackWhiteIp).where(BlackWhiteIp.ip == ip_info.ip))
    black_white_ip = result.scalar_one_or_none()
    if black_white_ip and black_white_ip.status == 0:
        return True

    result = await db.execute(select(BlackWhiteDevice).where(BlackWhiteDevice.device_id == device_id))
    black_white_device = result.scalar_one_or_none()
    if black_white_device and black_white_device.status == 0:
        return True

    is_review_user = False
    if len(ip_info.country) == 0 and len(ip_info.isp) == 0:
        is_review_user = True

    if not is_review_user:
        isp = ip_info.isp.lower()
        if "google" in isp or "apple" in isp:
            is_review_user = True

    if not is_review_user:
        agent_lower = agent.lower()
        is_device_check = "pad" in agent_lower or "tab" in agent_lower or "pixel" in agent_lower or "oneplus" in agent_lower or "google" in agent_lower
        is_country_check = ip_info.country in ["美国", "印度", "菲律宾"]
        if is_device_check and is_country_check:
            is_review_user = True

    if is_review_user:
        black_white_ip = BlackWhiteIp(
            ip=ip_info.ip,
            status=0,
            remarks=f"用户{user_id}注册IP归属ISP为{ip_info.isp}",
        )
        black_white_device = BlackWhiteDevice(
            device_id=device_id,
            status=0,
            remarks=f"用户{user_id}注册IP国家为[{ip_info.country}],设备为[{agent}]",
        )
        black_white_user = BlackWhiteUser(
            user_id=user_id,
            status=0,
            remarks=f"注册IP国家为[{ip_info.country}],ISP为{ip_info.isp},设备为[{agent}]",
        )

        db.add(black_white_ip)
        db.add(black_white_device)
        db.add(black_white_user)
        return True

    return is_review_user


async def _create_user(request: Request, db: AsyncSession, package_name: str, google_user: Optional[GoogleUserInfo] = None) -> dict:
    """Create a new user in the database."""
    device_id = request.headers.get("device-id")
    agent = request.headers.get("user-agent")
    user_id = random.randint(1000000, 9999999) + 80000000
    client_ip = _get_client_real_ip(request)
    ip_info = await asyncio.to_thread(ip_location.get_ip_location, client_ip)
    
    # Check if package_name exists in app_list
    result = await db.execute(select(AppList).where(AppList.package_name == package_name))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Invalid package_name")
    
    is_review = await _check_review_user(db, user_id, device_id, agent, ip_info)

    agent_model = UserAgent(agent)
    if not is_review:
        result = await db.execute(
            select(AppReview).where(
                AppReview.package_name == package_name,
                AppReview.app_version == agent_model.app_version,
            )
        )
        is_review = result.scalar_one_or_none() is not None

    if google_user:
        nickname = google_user.nickname if google_user.nickname else f"User{user_id}"
        google_id = google_user.user_id
        email = google_user.email
        avatar = google_user.avatar
    else:
        nickname = f"User{user_id}"
        google_id = None
        email = None
        avatar = None

    user = User(
        user_id=user_id,
        device_id=device_id,
        package_name=package_name,
        ip=client_ip,
        country=ip_info.country,
        nickname=nickname,
        google_id=google_id,
        email=email,
        avatar=avatar,
        agent=agent,
        is_review=is_review,
    )
    db.add(user)

    user_dict = user.to_dict()
    follows_result = await db.execute(select(UserFollow).where(UserFollow.user_id == user_id))
    fans_result = await db.execute(select(UserFollow).where(UserFollow.follow_user_id == user_id))
    likes_result = await db.execute(select(UserLike).where(UserLike.like_user_id == user_id))
    user_dict["follow_count"] = len(follows_result.scalars().all())
    user_dict["fans_count"] = len(fans_result.scalars().all())
    user_dict["like_count"] = len(likes_result.scalars().all())

    return user_dict


async def _query_user(request: Request, db: AsyncSession, package_name: str, user: User) -> dict:
    """Query an existing user in the database."""
    device_id = request.headers.get("device-id")
    agent = request.headers.get("user-agent")
    client_ip = _get_client_real_ip(request)
    ip_info = await asyncio.to_thread(ip_location.get_ip_location, client_ip)
    is_review = await _check_review_user(db, user.user_id, device_id, agent, ip_info)

    agent_model = UserAgent(agent)
    if not is_review:
        result = await db.execute(
            select(AppReview).where(
                AppReview.package_name == package_name,
                AppReview.app_version == agent_model.app_version,
            )
        )
        is_review = result.scalar_one_or_none() is not None

    user.is_review = is_review

    user_dict = user.to_dict()
    follows_result = await db.execute(select(UserFollow).where(UserFollow.user_id == user.user_id))
    fans_result = await db.execute(select(UserFollow).where(UserFollow.follow_user_id == user.user_id))
    likes_result = await db.execute(select(UserLike).where(UserLike.like_user_id == user.user_id))
    user_dict["follow_count"] = len(follows_result.scalars().all())
    user_dict["fans_count"] = len(fans_result.scalars().all())
    user_dict["like_count"] = len(likes_result.scalars().all())

    return user_dict


@router.post("/loginGoogle")
async def login_google(request: Request, data: GoogleUserInfo, db: AsyncSession = Depends(get_db)):
    """Login or register a user using Google account."""
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")

    result = await db.execute(select(User).where(User.google_id == str(data.user_id)))
    user = result.scalar_one_or_none()
    if not user and data.email:
        result = await db.execute(select(User).where(User.email == str(data.email)))
        user = result.scalar_one_or_none()

    if user:
        user_dict = await _query_user(request, db, package_name, user)
        token = create_token({"sub": str(user.user_id)})
        return {"code": 200, "data": {"accessToken": token, "user": user_dict}}

    user_dict = await _create_user(request, db, package_name, data)
    token = create_token({"sub": str(user_dict["user_id"])})
    return {"code": 200, "data": {"accessToken": token, "user": user_dict}}


@router.post("/loginGuest")
async def login_guest(request: Request, db: AsyncSession = Depends(get_db)):
    """Login as a guest user with device_id from request header."""
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")

    result = await db.execute(select(User).where(User.device_id == device_id))
    user = result.scalar_one_or_none()
    if user:
        user_dict = await _query_user(request, db, package_name, user)
        token = create_token({"sub": str(user.user_id)})
        return {"code": 200, "data": {"accessToken": token, "user": user_dict}}

    user_dict = await _create_user(request, db, package_name, None)
    token = create_token({"sub": str(user_dict["user_id"])})
    return {"code": 200, "data": {"accessToken": token, "user": user_dict}}


@router.post("/loginPassword")
async def login_password(request: Request, data: PasswordLoginRequest, db: AsyncSession = Depends(get_db)):
    """Login using user_id and password."""
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")

    result = await db.execute(select(User).where(User.user_id == data.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.password:
        raise HTTPException(status_code=401, detail="Invalid password")

    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    user_dict = await _query_user(request, db, package_name, user)
    token = create_token({"sub": str(user.user_id)})
    return {"code": 200, "data": {"accessToken": token, "user": user_dict}}


@router.post("/changePassword")
async def change_password(data: ChangePasswordRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Change user password."""
    if not user.password:
        raise HTTPException(status_code=400, detail="Password not set for this user")

    if not verify_password(data.old_password, user.password):
        raise HTTPException(status_code=401, detail="Invalid old password")

    user.password = get_hash(data.new_password)

    return {"code": 200, "data": {"message": "Password changed successfully"}}


@router.post("/setPassword")
async def set_password(data: SetPasswordRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Set user password for the first time."""
    if user.password:
        raise HTTPException(status_code=400, detail="Password already set. Use changePassword instead.")

    user.password = get_hash(data.password)

    return {"code": 200, "data": {"message": "Password set successfully"}}
