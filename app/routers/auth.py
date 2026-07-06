"""
Authentication routes: register and login.
"""

import random
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, AppList
from app.security import create_token
from app.schemas import GoogleLogin
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["auth"])

class IPInfoResp(BaseModel):
    success: bool
    ip: str | None = None
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    asn: str | None = None
    isp: str | None = None
    message: str | None = None

def get_client_real_ip(request: Request) -> str:
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


def query_ip_online(ip: str) -> IPInfoResp:
    """调用海外稳定接口 ipapi.co，无需离线库"""
    try:
        timeout = 6
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=timeout)
        data = resp.json()

        # 接口返回错误标记
        if "error" in data:
            return IPInfoResp(
                success=False,
                ip=ip,
                message=f"Lookup failed: {data.get('reason', 'invalid ip')}"
            )

        return IPInfoResp(
            success=True,
            ip=data.get("ip"),
            country=data.get("country_name"),
            country_code=data.get("country_code"),
            region=data.get("region"),
            city=data.get("city"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            asn=data.get("asn"),
            isp=data.get("org")
        )

    except requests.exceptions.RequestException as e:
        return IPInfoResp(
            success=False,
            ip=ip,
            message=f"External API request error: {str(e)}"
        )
    except Exception as e:
        return IPInfoResp(
            success=False,
            ip=ip,
            message=f"Server internal error: {str(e)}"
        )


def query_ip_china(ip):
    try:
        timeout = 6
        resp = requests.get(f"http://ip-api.com/json/{ip}?lang=en", timeout=timeout)
        data = resp.json()
        if data["status"] != "success":
            return IPInfoResp(success=False, ip=ip, message=data.get("message", "no data"))
        return IPInfoResp(
            success=True,
            ip=data["query"],
            country=data["country"],
            country_code=data["countryCode"],
            region=data["regionName"],
            city=data["city"],
            latitude=data["lat"],
            longitude=data["lon"],
            asn=str(data.get("as")),
            isp=data["isp"]
        )
    except requests.exceptions.RequestException as e:
        return IPInfoResp(
            success=False,
            ip=ip,
            message=f"External API request error: {str(e)}"
        )
    except Exception as e:
        return IPInfoResp(
            success=False,
            ip=ip,
            message=f"Server internal error: {str(e)}"
        )

def get_ip_info(client_ip: str) -> IPInfoResp:
    info = query_ip_online(client_ip)
    if not info.success:
        return query_ip_china(client_ip)
    return info

@router.post("/loginGoogle")
def login_google(request: Request, data: GoogleLogin, db: Session = Depends(get_db)):
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

    user_id = random.randint(1000000, 9999999) + 80000000
    nickname = data.nickname if data.nickname else f"User{user_id}"
    client_ip = get_client_real_ip(request)
    ip_info = get_ip_info(client_ip)

    # app_info = db.query(AppList).filter(AppList.id == package.id).first()
    is_check = 'Google' in ip_info.isp or 'Apple' in ip_info.isp
    agent = request.headers.get("user-agent")
    user = User(
        user_id=user_id, 
        device_id=device_id, 
        app_id=package.id, 
        ip=client_ip, 
        country=ip_info.country, 
        is_check=is_check, 
        nickname=nickname,
        email=data.email,
        google_id=data.user_id,
        avatar=data.avatar,
        agent=agent
    )
    db.add(user)
    db.commit()
    db.refresh(user)

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
    
    user_id = random.randint(1000000, 9999999) + 80000000
    nickname = f"User{user_id}"
    client_ip = get_client_real_ip(request)
    ip_info = get_ip_info(client_ip)
    is_check = 'Google' in ip_info.isp or 'Apple' in ip_info.isp
    agent = request.headers.get("user-agent")
    user = User(
        user_id=user_id, 
        device_id=device_id, 
        app_id=package.id, 
        ip=client_ip, 
        country=ip_info.country, 
        is_check=is_check, 
        nickname=nickname,
        agent=agent
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token({"sub": str(user.user_id)})
    return {
        "code": 200,
        "data": {"accessToken": token, "user": user.to_dict()}
    }
