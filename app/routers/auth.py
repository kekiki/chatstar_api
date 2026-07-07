"""
Authentication routes: register and login.
"""

import random
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, AppList
from app.security import create_token
from app.schemas import GoogleUserInfo
from app.ip_location import ip_location, IPLocation

router = APIRouter(prefix="/api", tags=["auth"])

def _get_client_real_ip(request: Request) -> str:
    """适配 Railway / Cloudflare / 通用代理 获取真实访客IP"""
    # Cloudflare 专用头
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    # Railway/通用 X-Forwarded-For
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first_ip = xff.split(",")[0].strip()
        return first_ip

    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()

    # 兜底
    return request.client.host

    # 谷歌用户注册国家为美国/印度/菲律宾&&设备为Pad/pixel/OnePlus/google属于审核人员，标记审核名单[账号类型/设备类型]
    # 苹果用户注册IP归属国家为[美国/爱尔兰/韩国/新加坡/以色列/印度/加拿大/澳大利亚]属于审核人员，标记审核名单[账号类型/IP类型]
def _check_review_user(db: Session, user_id: int, device_id: str, agent: str, ip_info: IPLocation = None):
    if ip_info:
        isp = ip_info.isp.lower() if ip_info.isp else ""
        if 'google' in isp or 'apple' in isp:
            return True
        
        # 检查设备类型
        agent_lower = agent.lower()
        is_device_check = 'pad' in agent_lower or 'tab' in agent_lower or 'pixel' in agent_lower or 'oneplus' in agent_lower or 'google' in agent_lower
        is_country_check = ip_info.country in ['美国', '印度', '菲律宾'] or ip_info.country in ['United States', 'India', 'Philippines']
        if is_device_check and is_country_check:
            return True

    return False

def _create_user(request: Request, db: Session, package_id: int, googleUser: GoogleUserInfo = None):
    """Create a new user in the database."""
    device_id = request.headers.get("device-id")
    agent = request.headers.get("user-agent")
    user_id = random.randint(1000000, 9999999) + 80000000
    nickname = googleUser.nickname if googleUser.nickname else f"User{user_id}"
    client_ip = _get_client_real_ip(request)
    ip_info = ip_location.get_ip_location(client_ip)
    is_check = _check_review_user(db, user_id, device_id, agent , ip_info)
    
    user = User(
        user_id=user_id,
        device_id=device_id,
        app_id=package_id,
        ip=client_ip,
        country=ip_info.addr,
        is_check=is_check,
        nickname=nickname,
        google_id=googleUser.user_id,
        email=googleUser.email,
        avatar=googleUser.avatar,
        agent=agent,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/loginGoogle")
def login_google(request: Request, data: GoogleUserInfo, db: Session = Depends(get_db)):
    """Login or register a user using Google account."""
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")

    package = db.query(AppList).filter(AppList.package_name == package_name).first()
    if not package:
        raise HTTPException(status_code=400, detail="Invalid package_name")

    user = db.query(User).filter(User.google_id == data.user_id).first()
    if not user and data.email:
        user = db.query(User).filter(User.email == data.email).first()

    if user:
        token = create_token({"sub": str(user.user_id)})
        return {
            "code": 200,
            "data": {"accessToken": token, "user": user.to_dict()}
        }

    user = _create_user(request, db, package.id, data)
    token = create_token({"sub": str(user.user_id)})
    return {
        "code": 200,
        "data": {"accessToken": token, "user": user.to_dict()}
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
        token = create_token({"sub": str(user.user_id)})
        return {
            "code": 200,
            "data": {"accessToken": token, "user": user.to_dict()}
        }
    
    user = _create_user(request, db, package.id, None)
    token = create_token({"sub": str(user.user_id)})
    return {
        "code": 200,
        "data": {"accessToken": token, "user": user.to_dict()}
    }
