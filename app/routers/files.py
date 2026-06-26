"""
files upload/download routes.
"""
from fastapi import APIRouter, UploadFile, File

from app.schemas import ZohoWorkDrive

router = APIRouter(prefix="/api", tags=["files"])

# 实例化 Zoho 工具
zoho = ZohoWorkDrive()

# 接口1：上传文件并返回直链
@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    result = zoho.upload_and_get_link(content, file.filename)
    return {
        "filename": file.filename,
        **result
    }

# 接口2：根据文件ID重新生成直链
@router.get("/link/{file_id}")
def get_file_link(file_id: str):
    return zoho.create_public_link(file_id)
