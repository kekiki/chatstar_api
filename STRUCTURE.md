# ChatStar API - 项目结构文档

## 📁 项目架构

项目采用模块化设计，便于扩展和维护：

```
chatstar_api/
├── main.py                    # 应用入口
├── Procfile                   # Railway 部署配置
├── requirements.txt           # Python 依赖
├── README.md                  # 项目文档
├── app/                       # 应用核心模块
│   ├── __init__.py
│   ├── config.py              # 配置模块（环境变量、常量）
│   ├── database.py            # 数据库配置和会话管理
│   ├── models/                # 数据模型
│   │   ├── __init__.py
│   │   └── user.py            # User SQLAlchemy 模型
│   ├── security/              # 认证和安全模块
│   │   ├── __init__.py
│   │   └── jwt.py             # JWT 和密码相关函数
│   ├── schemas/               # Pydantic 模型（预留扩展）
│   │   └── __init__.py
│   └── routers/               # API 路由
│       ├── __init__.py
│       ├── auth.py            # 认证路由（注册、登录）
│       ├── users.py           # 用户路由（用户信息）
│       └── web.py             # 网页路由（法律页面）
└── web/                       # 静态 HTML 页面
    ├── terms.html             # 服务条款
    ├── privacy.html           # 隐私政策
    └── child-safety.html      # 儿童安全政策
```

## 🏗️ 模块说明

### `config.py`
- 存放所有配置参数
- 从环境变量读取 PORT、DATABASE_URL、SECRET_KEY
- JWT 算法和过期时间配置

### `database.py`
- 数据库引擎创建（支持 SQLite 和 PostgreSQL/MySQL）
- SessionLocal 会话工厂
- `get_db()` 依赖注入函数

### `models/user.py`
- User SQLAlchemy ORM 模型
- 字段：id, hashed_password, device_id

### `security/jwt.py`
- 密码加密和验证（bcrypt）
- JWT token 创建和验证
- `current_user()` 依赖注入函数

### `routers/auth.py`
- `/api/register` - 用户注册（device_id 从请求头读取）
- `/api/login` - 用户登录（返回 JWT token）

### `routers/users.py`
- `/api/user/info` - 获取当前用户信息（需要 Bearer token）

### `routers/web.py`
- `/terms` - 服务条款页面
- `/privacy` - 隐私政策页面
- `/child-safety` - 儿童安全政策页面

## 🚀 使用方式

### 运行应用
```bash
uvicorn main:app --reload --port 8080
```

### 注册用户
```bash
curl -X POST http://localhost:8080/api/register \
  -H "device-id: your-device-id"
```

### 登录
```bash
curl -X POST http://localhost:8080/api/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=1&password=<password>"
```

### 获取用户信息
```bash
curl -X GET http://localhost:8080/api/user/info \
  -H "Authorization: Bearer <access_token>"
```

## 📝 API 文档

启动应用后，访问以下地址：
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`

## 🔧 扩展建议

1. **添加更多模型**
   - 在 `app/models/` 中创建新文件（如 `message.py`）

2. **添加新 API 路由**
   - 在 `app/routers/` 中创建新文件，然后在 `main.py` 中注册

3. **添加 Pydantic schemas**
   - 在 `app/schemas/` 中创建请求/响应模型

4. **添加工具函数**
   - 创建 `app/utils/` 目录，放置通用工具函数

## 📦 依赖管理

当前 requirements.txt 包含：
- FastAPI - Web 框架
- SQLAlchemy - ORM
- PyJWT - JWT 处理
- passlib - 密码加密
- bcrypt - 加密算法
- python-multipart - 表单数据解析
- uvicorn - ASGI 服务器

## 🌐 部署到 Railway

项目已配置可直接部署到 Railway：
```bash
git push
```

Railway 将自动读取 `Procfile` 启动应用。

---

**维护者**: ChatStar Team  
**最后更新**: 2026-06-08
