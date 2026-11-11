# ChatStar API

A lightweight FastAPI service for user authentication and profile access.

## AI 聊天配置

AI 聊天使用 OpenAI 兼容的 Chat Completions 接口，可接入 OpenAI 或其他兼容服务。
在 `.env` 或部署环境变量中配置：

```dotenv
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4o-mini
```

- `OPENAI_BASE_URL`：API 根地址，默认 `https://api.openai.com/v1`。请填写服务商提供的根路径（通常包含 `/v1`），不要填写完整的 `/chat/completions` 地址。
- `OPENAI_API_KEY`：服务商的 API Key，生产环境必填。
- `OPENAI_MODEL`：服务商支持的模型 ID，默认 `gpt-4o-mini`。

修改配置后需重启服务。旧的 `GROQ_API_KEY` 不再使用，请迁移到以上配置。
如需继续使用 Groq，可将根地址设为 `https://api.groq.com/openai/v1`，并填写对应的 Key 和模型 ID（如 `openai/gpt-oss-20b`）。
`ENV_MODE=develop` 时仍使用本地随机模拟回复，不会调用 AI 服务，也不需要配置 API Key；验证真实接口时需使用非 `develop` 环境。

## 在虚拟环境运行项目

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