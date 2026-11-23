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

## Google Play 内购订单绑定

发货前，`/api/order/verify` 会将 Google Play 服务端返回的 `obfuscatedExternalProfileId`
与后台订单的 `transaction_no` 核对；不一致则拒绝发货。当前 Flutter 支付流程会在发起支付时传入此值。

默认也拒绝没有该字段的成功购买。如确需兼容未传该字段的历史购买，可设置
`GOOGLE_PLAY_LEGACY_PROFILE_ID_CUTOFF` 为客户端开始传入该字段的 Unix 时间戳（秒）。
只有后台订单创建时间和 Google 返回的购买时间都严格早于该时间点，才允许按旧流程补单。
没有确认过切换时间时，保持该变量不设置。

### 退款通知与补单

- Play Console 手动退款时，若希望自动回收道具或 VIP，使用同时撤销购买的选项。仅退款的订单可能不会出现在 Google 的作废购买列表里。
- 在 Play Console 发送 RTDN 测试通知，并确认 Fly 日志有 `rtdn: test notification received`。后端直连测试不能替代 Pub/Sub 投递检查。
- 成功回收时，后端保存一条系统消息；有钻石扣回时，消息显示实际扣除的数量。重复通知不会重复扣回或保存消息。
- 对于已退款、且确实需要撤销权益但未自动处理的单笔订单，可在具备数据库和 Google Play 凭据的后端环境运行：

  ```bash
  python -m scripts.reconcile_google_refund <后台订单号> --confirm-revoke
  ```

  脚本会向 Google 核对原订单和购买凭据，只处理确认全额退款、且本地仍是已支付的订单。不会再次向 Google 发起退款，也不会开启轮询。

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
