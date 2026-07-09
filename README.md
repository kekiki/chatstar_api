# ChatStar API

A lightweight FastAPI service for user authentication and profile access.

## Available endpoints

### Authentication
- `POST /api/register`
  - Register or create a guest user using `device-id` in request header.
- `POST /api/loginGuest`
  - Guest login using `device-id` header.
  - Returns a JWT access token.
- `POST /api/loginGoogle`
  - Login or register using a Google ID token payload.
  - Returns a JWT access token.

### User info
- `GET /api/user/info`
  - Requires `Authorization: Bearer <access_token>`.
  - Returns authenticated user details.
- `GET /api/users`
  - Requires `Authorization: Bearer <access_token>`.
  - Returns a paginated user list.

## Example usage

### Register guest user
```bash
curl -X POST http://localhost:8080/api/register \
  -H "device-id: your-device-id"
```

### Login as guest
```bash
curl -X POST http://localhost:8080/api/loginGuest \
  -H "device-id: your-device-id"
```

### Login with Google
```bash
curl -X POST http://localhost:8080/api/loginGoogle \
  -H "Content-Type: application/json" \
  -d '{"id_token":"<google-id-token>"}'
```

### Get current user info
```bash
curl -X GET http://localhost:8080/api/user/info \
  -H "Authorization: Bearer <access_token>"
```

## Notes
- The old password login endpoint is currently commented out in `app/routers/auth.py`.
- JWT authentication now uses bearer tokens via `Authorization: Bearer <token>`.


##在虚拟环境运行项目
1.进入你的项目文件夹
```bash
cd ~/你的项目文件夹
```

2. 创建名为 .venv 可访问全局包的虚拟环境
```bash
python -m venv .venv --system-site-packages
```

3.激活虚拟环境（Mac zsh）,激活成功后，终端前缀会出现 (venv) 标识。
```bash
source .venv/bin/activate
```

4.在虚拟环境里执行 Python /pip 命令
```bash
python -m pip install -r requirements.txt
```

5.退出虚拟环境
```bash
deactivate
```