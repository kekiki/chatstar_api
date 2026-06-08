from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import uuid
import os

# ===================== 自动读取 Railway 环境变量 =====================
PORT = int(os.environ.get("PORT", 8080))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "default-secret-key")

# ===================== 智能数据库 =====================
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ===================== 用户表 =====================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    device_id = Column(String, unique=True, index=True)

Base.metadata.create_all(bind=engine)

# ===================== JWT 认证 =====================
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_hash(password):
    return pwd_context.hash(password)

def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=30)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "无效授权")
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(401, "用户不存在")
        return user
    except JWTError:
        raise HTTPException(401, "令牌失效")

# ===================== 应用 =====================
app = FastAPI(title="Railway FastAPI")

@app.get("/")
def home():
    return {"status": "ok", "source": "railway"}

@app.post("/api/register")
def register(request: Request, db: Session = Depends(get_db)):
    device_id = request.headers.get("device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="缺少 device_id 请求头")

    if db.query(User).filter(User.device_id == device_id).first():
        raise HTTPException(400, "设备已注册")
    
    user_id = str(uuid.uuid4())
    password = str(uuid.uuid4())[:8]
    hashed = get_hash(password)

    user = User(user_id=user_id, hashed_password=hashed, device_id=device_id)
    db.add(user)
    db.commit()

    return {
        "code": 200,
        "data": {"user_id": user_id, "password": password}
    }

@app.post("/api/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "账号或密码错误")
    
    token = create_token({"sub": user.user_id})
    return {
        "code": 200,
        "data": {"access_token": token, "token_type": "bearer"}
    }

@app.get("/api/user/info")
def info(user: User = Depends(current_user)):
    return {
        "code": 200,
        "data": {"user_id": user.user_id, "device_id": user.device_id}
    }