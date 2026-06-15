import requests
from fastapi import HTTPException
from pydantic_settings import BaseSettings

# 加载配置
class ZohoSettings(BaseSettings):
    ZOHO_CLIENT_ID: str
    ZOHO_CLIENT_SECRET: str
    ZOHO_REFRESH_TOKEN: str
    ZOHO_ACCOUNT_URL: str
    ZOHO_ORG_ID: str
    ZOHO_ROOT_FOLDER_ID: str

    class Config:
        env_file = ".env"

zoho_cfg = ZohoSettings()

# 全局缓存 access_token
_ACCESS_TOKEN_CACHE = ""

class ZohoWorkDrive:
    def __init__(self):
        self.cfg = zoho_cfg
        self.token = self._get_valid_token()

    def _refresh_token(self) -> str:
        """使用 refresh_token 刷新新的 access_token"""
        url = f"{self.cfg.ZOHO_ACCOUNT_URL}/oauth/v2/token"
        data = {
            "client_id": self.cfg.ZOHO_CLIENT_ID,
            "client_secret": self.cfg.ZOHO_CLIENT_SECRET,
            "refresh_token": self.cfg.ZOHO_REFRESH_TOKEN,
            "grant_type": "refresh_token"
        }
        try:
            resp = requests.post(url, data=data, timeout=30)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Zoho鉴权网络异常: {str(e)}")

        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"刷新Token失败 {resp.status_code}: {resp.text}")
        
        json_data = resp.json()
        new_token = json_data.get("access_token")
        if not new_token:
            raise HTTPException(status_code=500, detail="未获取到access_token")
        return new_token

    def _get_valid_token(self) -> str:
        """获取有效token，无缓存/失效则刷新"""
        global _ACCESS_TOKEN_CACHE
        if not _ACCESS_TOKEN_CACHE:
            _ACCESS_TOKEN_CACHE = self._refresh_token()
        return _ACCESS_TOKEN_CACHE

    def upload_file(self, file_bytes: bytes, filename: str) -> str:
        """
        上传文件到指定文件夹
        :param file_bytes: 文件二进制流
        :param filename: 原始文件名
        :return: file_id 文件唯一ID
        """
        upload_api = "https://workdrive.zohoapi.com/v1/upload"
        headers = {"Authorization": f"Zoho-oauthtoken {self.token}"}
        form_data = {
            "orgId": self.cfg.ZOHO_ORG_ID,
            "folderId": self.cfg.ZOHO_ROOT_FOLDER_ID
        }
        files = {"file": (filename, file_bytes)}

        try:
            resp = requests.post(
                upload_api,
                headers=headers,
                data=form_data,
                files=files,
                timeout=60
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"文件上传请求异常: {str(e)}")
        
        # token过期自动重试一次
        if resp.status_code == 401:
            _ACCESS_TOKEN_CACHE = self._refresh_token()
            headers["Authorization"] = f"Zoho-oauthtoken {self.token}"
            resp = requests.post(upload_api, headers=headers, data=form_data, files=files, timeout=60)

        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"上传失败 {resp.status_code}: {resp.text}")
        
        res_data = resp.json()
        file_id = res_data["data"][0]["id"]
        return file_id

    def create_public_link(self, file_id: str, expire_time: str = "") -> dict:
        """
        生成公开永久下载直链
        :param file_id: 文件ID
        :param expire_time: 过期时间戳，空=永久
        :return: 包含直链、文件ID的字典
        """
        share_api = f"https://workdrive.zohoapi.com/v1/files/{file_id}/share"
        headers = {
            "Authorization": f"Zoho-oauthtoken {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "orgId": self.cfg.ZOHO_ORG_ID,
            "shareType": "public",
            "permissions": {
                "view": True,
                "download": True
            },
            "expiry": expire_time
        }

        try:
            resp = requests.post(share_api, headers=headers, json=payload, timeout=30)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建分享链接异常: {str(e)}")

        # token失效重试
        if resp.status_code == 401:
            _ACCESS_TOKEN_CACHE = self._refresh_token()
            headers["Authorization"] = f"Zoho-oauthtoken {self.token}"
            resp = requests.post(share_api, headers=headers, json=payload, timeout=30)

        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"生成直链失败 {resp.status_code}: {resp.text}")
        
        data = resp.json()["data"]
        return {
            "file_id": file_id,
            "direct_url": data["publicUrl"],
            "share_info": data
        }

    def upload_and_get_link(self, file_bytes: bytes, filename: str) -> dict:
        """一站式：上传文件 + 自动生成公开直链"""
        fid = self.upload_file(file_bytes, filename)
        link_info = self.create_public_link(fid)
        return link_info