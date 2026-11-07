FROM python:3.11-slim

WORKDIR /app

# 安装依赖前置
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 启动命令，和你最开始那行Procfile参数完全对齐
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--loop", "uvloop", "--ws-ping-interval", "20", "--ws-ping-timeout", "60"]
