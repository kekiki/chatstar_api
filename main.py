from fastapi import FastAPI, Depends, HTTPException, status
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
from dotenv import load_dotenv
from fastapi.responses import HTMLResponse

# 加载环境变量
load_dotenv()

# Fly.io 自动分配端口
PORT = int(os.getenv("PORT", 8080))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# 智能数据库：本地SQLite / 线上PostgreSQL
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 用户表模型
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    device_id = Column(String, unique=True, index=True)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

Base.metadata.create_all(bind=engine)

# JWT 配置
SECRET_KEY = os.getenv("SECRET_KEY", str(uuid.uuid4()))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30

# 密码工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# DB 会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 登录校验
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效授权")
    except JWTError:
        raise HTTPException(status_code=401, detail="令牌已失效")
    
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user

# 请求模型
class RegisterRequest(BaseModel):
    device_id: str

# 应用初始化
app = FastAPI(title="APP API Server", version="fly-1.0")

# 用户协议
@app.get("/agreement", response_class=HTMLResponse)
def agreement():
    return "<h1>用户协议</h1><p>仅收集设备标识，自动注册账号</p>"

# 隐私政策
@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return "<h1>隐私政策</h1><p>数据加密存储，不泄露第三方</p>"

# 注册接口
@app.post("/api/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.device_id == req.device_id).first()
    if exists:
        raise HTTPException(status_code=400, detail="设备已注册")

    user_id = str(uuid.uuid4())
    password = str(uuid.uuid4())[:8]
    hashed_pw = get_password_hash(password)

    user = User(
        user_id=user_id,
        hashed_password=hashed_pw,
        device_id=req.device_id
    )
    db.add(user)
    db.commit()

    return {
        "code": 200,
        "msg": "注册成功",
        "data": {"user_id": user_id, "password": password}
    }

# 登录接口
@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="账号或密码错误")

    token = create_access_token({"sub": user.user_id})
    return {
        "code": 200,
        "msg": "登录成功",
        "data": {"access_token": token, "token_type": "bearer"}
    }

# 获取用户信息
@app.get("/api/user/info")
def user_info(current_user: User = Depends(get_current_user)):
    return {
        "code": 200,
        "msg": "获取成功",
        "data": {
            "user_id": current_user.user_id,
            "device_id": current_user.device_id,
            "created_at": current_user.created_at
        }
    }

# 健康检查
@app.get("/")
def home():
    return {"status": "running", "app": "fly-fastapi-app"}