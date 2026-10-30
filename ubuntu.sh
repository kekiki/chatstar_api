#!/bin/bash
set -e
read -p "请输入你的域名（例如 api.xxx.com）: " DOMAIN
read -p "你的Github仓库git地址: " GIT_REPO
read -p "R2_ACCOUNT_ID: " R2_ACCOUNT_ID
read -p "R2_ACCESS_KEY_ID: " R2_ACCESS_KEY_ID
read -p "R2_SECRET_ACCESS_KEY: " R2_SECRET_ACCESS_KEY
read -p "R2_BUCKET_NAME: " R2_BUCKET_NAME
read -p "R2_CUSTOM_DOMAIN: " R2_CUSTOM_DOMAIN

# 更新系统
apt update && apt upgrade -y
apt install -y git curl software-properties-common

# 安装docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker $USER
systemctl enable docker
systemctl start docker

# 安装docker-compose
apt install -y docker-compose-plugin

# 安装nginx + certbot
apt install -y nginx certbot python3-certbot-nginx
systemctl enable nginx
systemctl stop nginx

# 清理默认nginx配置
rm -f /etc/nginx/sites-enabled/default
rm -f /etc/nginx/sites-available/default

# 写入nginx配置（支持WebSocket）
cat > /etc/nginx/sites-available/fastapi <<EOF
server {
    listen 80;
    server_name ${DOMAIN};
    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name ${DOMAIN};
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket核心配置
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
EOF
ln -s /etc/nginx/sites-available/fastapi /etc/nginx/sites-enabled/

# 申请SSL证书
certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN}

# 证书自动续期定时任务
echo "0 3 * * * certbot renew --quiet && systemctl reload nginx" | crontab -

# 项目目录
mkdir -p /opt/fastapi-api
cd /opt/fastapi-api

# 拉取代码
git clone ${GIT_REPO} .

# 写入环境变量
cat > .env <<EOF
R2_ACCOUNT_ID=${R2_ACCOUNT_ID}
R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}
R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}
R2_BUCKET_NAME=${R2_BUCKET_NAME}
R2_CUSTOM_DOMAIN=${R2_CUSTOM_DOMAIN}
EOF

# Dockerfile（和你之前一致）
cat > Dockerfile <<EOF
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1", "--ws-ping-interval", "20", "--ws-ping-timeout", "60"]
EOF

# docker-compose.yml
cat > docker-compose.yml <<EOF
version: "3"
services:
  api:
    build: .
    restart: always
    env_file: .env
    ports:
      - "127.0.0.1:8000:8000"
EOF

# 启动服务
docker compose up -d
systemctl start nginx

echo "====================================="
echo "✅ 部署完成！"
echo "API地址：https://${DOMAIN}"
echo "WS地址：wss://${DOMAIN}/api/ws/connect?token=xxx"
echo "文档地址：https://${DOMAIN}/docs"
echo "====================================="
