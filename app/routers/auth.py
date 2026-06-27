"""
Authentication routes: register and login.
"""
import json
import time
import random
import urllib.error
import urllib.parse
import urllib.request
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import GOOGLE_CLIENT_ID
from app.database import get_db
from app.models import User, AppList
from app.security import create_token
from app.schemas import GoogleLoginRequest
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

    token = create_token({"sub": user.user_id})
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
    
    client_ip = get_client_real_ip(request)
    ip_info = get_ip_info(client_ip)
    is_check = 'Google' in ip_info.isp or 'Apple' in ip_info.isp
    user = User(device_id=device_id, app_id=package.id, ip=client_ip, country=ip_info.country, is_check=is_check)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token({"sub": user.id})
    return {
        "code": 200,
        "data": {"accessToken": token}
    }
