"""
Authentication routes: register and login.
"""

import random
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, AppList, BlackWhiteUser, BlackWhiteIp, BlackWhiteDevice, UserFollow, UserLike, Media
from app.security import create_token, get_hash, verify_password
from app.schemas import GoogleUserInfo
from app.ip_location import ip_location, IPLocation
from pydantic import BaseModel
import asyncio

router = APIRouter(prefix="/api", tags=["auth"])

class PasswordLoginRequest(BaseModel):
    user_id: int
    password: str

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

    # 检查用户是否在审核名单中
    black_white_user = db.query(BlackWhiteUser).filter(BlackWhiteUser.user_id == str(user_id)).first()
    if black_white_user and black_white_user.status == 0:
        return True
    
    # 检查IP是否在审核名单中
    black_white_ip = db.query(BlackWhiteIp).filter(BlackWhiteIp.ip == ip_info.ip).first()
    if black_white_ip and black_white_ip.status == 0:
        return True
    
    # 检查设备是否在审核名单中
    black_white_device = db.query(BlackWhiteDevice).filter(BlackWhiteDevice.device_id == device_id).first()
    if black_white_device and black_white_device.status == 0:
        return True

    if ip_info:
        isp = ip_info.isp.lower() if ip_info.isp else ""
        if 'google' in isp or 'apple' in isp:
            # ip记录到审核名单
            black_white_ip = BlackWhiteIp(
                ip=ip_info.ip,
                status=0,
                remarks=f"用户{user_id}注册IP归属ISP为{isp}"
            )
            db.add(black_white_ip)
            db.commit()
            
            # 用户记录到审核名单
            black_white_user = BlackWhiteUser(
                user_id=user_id,
                status=0,
                remarks=f"注册IP归属ISP为{isp}"
            )
            db.add(black_white_user)
            db.commit()
            return True
        
        # 检查设备类型
        agent_lower = agent.lower()
        is_device_check = 'pad' in agent_lower or 'tab' in agent_lower or 'pixel' in agent_lower or 'oneplus' in agent_lower or 'google' in agent_lower
        is_country_check = ip_info.country in ['美国', '印度', '菲律宾']
        if is_device_check and is_country_check:
            # 设备记录到审核名单
            black_white_device = BlackWhiteDevice(
                device_id=device_id,
                status=0,
                remarks=f"用户{user_id}注册设备为[{agent}]，注册IP归属地为[{ip_info.addr}]"
            )
            db.add(black_white_device)
            db.commit()
            
            # 用户记录到审核名单
            black_white_user = BlackWhiteUser(
                user_id=user_id,
                status=0,
                remarks=f"注册设备为[{agent}]，注册IP归属地为[{ip_info.addr}]"
            )
            db.add(black_white_user)
            db.commit()
            return True

    return False

async def _create_user(request: Request, db: Session, package_name: str, googleUser: GoogleUserInfo = None) -> dict:
    """Create a new user in the database."""
    device_id = request.headers.get("device-id")
    agent = request.headers.get("user-agent")
    user_id = random.randint(1000000, 9999999) + 80000000
    client_ip = _get_client_real_ip(request)
    # ip_info = ip_location.get_ip_location(client_ip)
    # czdb 查询是同步 IO，高并发场景放到线程池执行，避免阻塞事件循环
    ip_info = await asyncio.to_thread(ip_location.get_ip_location, client_ip)
    is_review = _check_review_user(db, user_id, device_id, agent , ip_info)
    if googleUser:
        nickname = googleUser.nickname if googleUser.nickname else f"User{user_id}"
        google_id = googleUser.user_id
        email = googleUser.email
        avatar = googleUser.avatar
        password = None
    else:
        nickname = f"User{user_id}"
        google_id = None
        email = None
        avatar = None
        # Generate random 6-character password for guest users
        password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))
    
    user = User(
        user_id=user_id,
        device_id=device_id,
        package_name=package_name,
        ip=ip_info.ip,
        country=ip_info.country,
        nickname=nickname,
        google_id=google_id,
        email=email,
        avatar=avatar,
        agent=agent,
        password=get_hash(password) if password else None,
    )
    db.add(user)
    db.commit()
    user_dict = user.to_dict()
    user_dict["r_flag"] = is_review

    # follow_count, fans_count, like_count
    follows = db.query(UserFollow).filter(UserFollow.user_id == str(user_id)).all()
    fans = db.query(UserFollow).filter(UserFollow.follow_user_id == str(user_id)).all()
    likes = db.query(UserLike).filter(UserLike.like_user_id == str(user_id)).all()
    user_dict["follow_count"] = len(follows)
    user_dict["fans_count"] = len(fans)
    user_dict["like_count"] = len(likes)

    return user_dict

async def _query_user(request: Request, db: Session, package_name: str, user: User) -> dict:
    """Query an existing user in the database."""
    device_id = request.headers.get("device-id")
    agent = request.headers.get("user-agent")
    client_ip = _get_client_real_ip(request)
    # ip_info = ip_location.get_ip_location(client_ip)
    # czdb 查询是同步 IO，高并发场景放到线程池执行，避免阻塞事件循环
    ip_info = await asyncio.to_thread(ip_location.get_ip_location, client_ip)
    is_review = _check_review_user(db, user.user_id, device_id, agent , ip_info)
    
    user_dict = user.to_dict()
    user_dict["r_flag"] = is_review

    # follow_count, fans_count, like_count
    follows = db.query(UserFollow).filter(UserFollow.user_id == str(user.user_id)).all()
    fans = db.query(UserFollow).filter(UserFollow.follow_user_id == str(user.user_id)).all()
    likes = db.query(UserLike).filter(UserLike.like_user_id == str(user.user_id)).all()
    user_dict["follow_count"] = len(follows)
    user_dict["fans_count"] = len(fans)
    user_dict["like_count"] = len(likes)

    return user_dict

@router.post("/loginGoogle")
def login_google(request: Request, data: GoogleUserInfo, db: Session = Depends(get_db)):
    """Login or register a user using Google account."""
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")

    # package = db.query(AppList).filter(AppList.package_name == package_name).first()
    # if not package:
    #     raise HTTPException(status_code=400, detail="Invalid package_name")

    user = db.query(User).filter(User.google_id == str(data.user_id)).first()
    if not user and data.email:
        user = db.query(User).filter(User.email == str(data.email)).first()

    if user:
        user_dict = asyncio.run(_query_user(request, db, package_name, user))
        token = create_token({"sub": str(user.user_id)})
        return {
            "code": 200,
            "data": {"accessToken": token, "user": user_dict}
        }

    user_dict = asyncio.run(_create_user(request, db, package_name, data))
    token = create_token({"sub": str(user_dict["user_id"])})
    return {
        "code": 200,
        "data": {"accessToken": token, "user": user_dict}
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

    # package = db.query(AppList).filter(AppList.package_name == package_name).first()
    # if not package:
    #     raise HTTPException(status_code=400, detail="Invalid package_name")

    user = db.query(User).filter(User.device_id == device_id).first()
    if user:
        user_dict = asyncio.run(_query_user(request, db, package_name, user))
        token = create_token({"sub": str(user.user_id)})
        return {
            "code": 200,
            "data": {"accessToken": token, "user": user_dict}
        }
    
    user_dict = asyncio.run(_create_user(request, db, package_name, None))
    token = create_token({"sub": str(user_dict["user_id"])})
    return {
        "code": 200,
        "data": {"accessToken": token, "user": user_dict}
    }


@router.post("/loginPassword")
def login_password(request: Request, data: PasswordLoginRequest, db: Session = Depends(get_db)):
    """Login using user_id and password."""
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id header")

    package_name = request.headers.get("package-name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Missing package_name header")

    # package = db.query(AppList).filter(AppList.package_name == package_name).first()
    # if not package:
    #     raise HTTPException(status_code=400, detail="Invalid package_name")

    user = db.query(User).filter(User.user_id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if not user.password:
        raise HTTPException(status_code=401, detail="Invalid password")
    
    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    user_dict = asyncio.run(_query_user(request, db, package_name, user))
    token = create_token({"sub": str(user.user_id)})
    return {
        "code": 200,
        "data": {"accessToken": token, "user": user_dict}
    }
