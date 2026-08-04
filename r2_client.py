
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from app.config import R2_ACCESS_KEY, R2_SECRET_KEY, R2_ACCOUNT_ID, R2_BUCKET_NAME, R2_ENDPOINT, WORKER_API_URL, R2_PUBLIC_DOMAIN
import httpx
from fastapi import HTTPException

_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(verify=False, timeout=30.0)
    return _http_client


class R2Client:
    def __init__(self):
        self.r2_client = boto3.client(
            's3',
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            endpoint_url=R2_ENDPOINT,
            region_name='auto',
            config=Config(signature_version='s3v4')
        )
        self.account_id = R2_ACCOUNT_ID
        self.end_point = R2_ENDPOINT
        self.bucket_name = R2_BUCKET_NAME

    async def get_r2_upload_url(self, file_name: str, content_type: str):
        client = await _get_http_client()
        resp = await client.post(
            WORKER_API_URL,
            headers={
                "Content-Type": "application/json",
            },
            json={
                "fileName": file_name,
                "contentType": content_type
            },
            timeout=10
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail="获取R2上传直链失败")

        return resp.json()

    async def put_file_to_r2(self, upload_url, file_bytes, content_type):
        client = await _get_http_client()
        resp = await client.put(
            upload_url,
            content=file_bytes,
            headers={"Content-Type": content_type}
        )
        return resp

    async def upload_bytes(self, file_bytes: bytes, object_key: str):
        try:
            self.r2_client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=object_key,
                Body=file_bytes
            )
            file_url = f"{R2_PUBLIC_DOMAIN}/{object_key}"
            return file_url
        except Exception as e:
            raise HTTPException(500, f"R2上传失败: {str(e)}")

    def delete_file(self, object_key: str):
        self.r2_client.delete_object(Bucket=self.bucket_name, Key=object_key)

    def file_exists(self, object_key: str) -> bool:
        try:
            self.r2_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError:
            return False

    def get_unique_key(self, origin_name: str) -> str:
        if "." in origin_name:
            ext = origin_name.split(".")[-1]
            return f"{uuid.uuid4()}.{ext}"
        return f"{uuid.uuid4()}"

    async def upload_and_get_link(self, file_bytes: bytes, file_name: str, file_content_type: str) -> dict:
        object_key = f'uploads/{self.get_unique_key(file_name)}'
        public_url = await self.upload_bytes(file_bytes, object_key)
        return {
            "url": public_url,
            "object_key": object_key
        }