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
- 在 Play Console 发送 RTDN 测试通知，并确认 Fly 日志有 `rtdn.test_received`。后端直连测试不能替代 Pub/Sub 投递检查。
- Google 验单或退款数据提供的订单号保存在 `google_order_id`，后台订单号在数据库中不变。订单历史和退款系统消息优先显示 Google 订单号；没有时才显示后台订单号。消息中的钻石数量为实际扣除数量。重复通知不会重复扣回或保存消息。
- 对于已退款、且确实需要撤销权益但未自动处理的单笔订单，可在具备数据库和 Google Play 凭据的后端环境运行：

  ```bash
  python -m scripts.reconcile_google_refund <后台订单号> --confirm-revoke
  ```

  脚本会向 Google 核对原订单和购买凭据，只处理确认全额退款、且本地仍是已支付的订单。不会再次向 Google 发起退款，也不会开启轮询。

## 查看日志

应用日志写入标准输出。本地默认是单行文本；Fly 使用单行 JSON。每条日志都有 UTC 日期时间、级别和事件名。HTTP 请求记录路由模板、状态码和耗时，成功的 `/health` 探针不记录。客户端可从响应头读取 `X-Request-ID`，再用它串起同一次请求的验证、业务和错误日志。

- `LOG_FORMAT`：`console`（默认）或 `json`。
- `LOG_LEVEL`：`DEBUG`、`INFO`（默认）、`WARNING`、`ERROR` 或 `CRITICAL`。`DEBUG` 会额外显示资产流水记录等细节。
- 请求日志不包含原始查询参数、请求体、认证头或客户端 IP。支付、聊天和外部服务事件只记录排查需要的元数据；异常日志保留类型和栈帧，不打印原始异常内容。此设置不删除旧日志。

在仓库根目录（已激活 `.venv`）运行：

```bash
# 只看最近的警告或错误，按北京时间显示
fly logs -a chatstar-api --no-tail --json | python -m scripts.filter_logs --level WARNING --timezone Asia/Shanghai

# 实时跟踪 Google 通知和退款
fly logs -a chatstar-api --json | python -m scripts.filter_logs --event rtdn --event refund

# 查一笔 Google 订单，也支持后台 O 开头的订单号
fly logs -a chatstar-api --no-tail --json | python -m scripts.filter_logs --order GPA.1234-5678-9012-34567

# 排查验单接口，也可改用 --request-id <响应头中的ID> 查同一次请求
fly logs -a chatstar-api --no-tail --json | python -m scripts.filter_logs --route /api/order/verify
```

`--event` 匹配事件名或事件前缀。常用事件：`http.validation_failed`（请求校验失败）、`order.verify.result`（验单结果）、`rtdn.voided_received`（收到作废通知）、`refund.processed`（退款回收已提交）、`refund.skipped`（跳过及原因）。单个业务事件未必包含路由、订单号或请求 ID：这些筛选条件只匹配有该字段的日志，可以先按订单号找到请求 ID，再用请求 ID 查看完整链路。

## 日活统计

`daily_user_activity` 按北京时间（`Asia/Shanghai`）记录非主播用户，每位用户每天最多一条。成功登录、通过会话鉴权并完成处理的 HTTP 请求，以及已认证用户建立 WebSocket 连接或发送应用层文本消息，都会记录活跃。连接保持空闲或仅有协议层心跳不算次日活跃。统计写入失败会记录日志，不回滚业务操作。

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

运行测试（包括使用本地 SQLite 的日活回归测试）：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

5.退出虚拟环境
```bash
deactivate
```
