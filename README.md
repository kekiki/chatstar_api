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

