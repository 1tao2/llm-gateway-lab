# Phase 1 Unified Provider SDK Design

## 目标

建立统一的异步 Provider 边界，使同一段业务代码可以调用 Mock、OpenAI-compatible 和智谱 Provider，而无需理解供应商 SDK、原始响应或 HTTP 异常。

Phase 1 只负责请求适配、响应归一化和异常映射。不实现 Router、Retry、Fallback、Circuit Breaker、流式输出或真实 API 压力测试。

## 技术边界

- 使用 Python 3.11+、Pydantic 和 HTTPX。
- 单元与协议集成测试不访问互联网，不产生模型费用。
- 智谱真实 E2E 默认跳过，只有显式设置 `RUN_ZHIPU_E2E=1` 且存在 `ZHIPU_API_KEY` 时才允许执行。
- API Key 只能来自环境变量或 `.env`，不得写入源码、测试数据、日志或 Git。
- Phase 0 的 `/health` 契约保持不变。

## 模块结构

```text
app/providers/
├── __init__.py
├── base.py
├── errors.py
├── schemas.py
├── mock.py
├── openai_compatible.py
└── zhipu.py

tests/providers/
├── __init__.py
├── test_contract.py
├── test_mock.py
├── test_openai_compatible.py
└── test_zhipu.py
```

现有未完成的 Provider 文件原地修正，不保留演示 `main()` 或占位实现。

## 统一数据契约

`ChatMessage` 包含 `role` 和非空 `content`。`role` 限定为 `system`、`user` 或 `assistant`。

`ChatRequest` 包含非空 `model` 和至少一条 `messages`。

`TokenUsage` 包含非负的 `prompt_tokens`、`completion_tokens` 和 `total_tokens`，缺失的供应商 usage 字段归一为 0。

`ChatResponse` 固定包含：

- `request_id: str`
- `provider: str`
- `model: str`
- `content: str`
- `latency_ms: float`，非负
- `usage: TokenUsage`

所有 Provider 均实现：

```python
async def chat(self, request: ChatRequest) -> ChatResponse:
    ...
```

业务层只消费该接口和统一模型。

## 统一异常契约

所有对外异常继承 `ProviderError`：

- `ProviderAuthenticationError`：HTTP 401/403。
- `ProviderRateLimitError`：HTTP 429。
- `ProviderServerError`：HTTP 5xx。
- `ProviderTimeoutError`：HTTPX timeout。
- `ProviderConnectionError`：HTTPX connection/network error。
- `ProviderInvalidResponseError`：成功状态下的非法 JSON、字段缺失或无法解析的数据。
- `ProviderConfigurationError`：缺失或非法 Provider 配置。
- `ProviderRequestError`：其他 HTTP 4xx 请求错误。

异常对象保留安全的 provider、状态码和错误类别信息，但不包含 API Key、Authorization header 或完整敏感响应体。HTTPX 与第三方 SDK 异常不得越过 Provider 边界。

## MockProvider

`MockProvider` 使用受约束的模式值，初始化时拒绝未知模式。必须支持：

- `normal`：返回完整 `ChatResponse`。
- `timeout`：抛出 `ProviderTimeoutError`。
- `429`：抛出 `ProviderRateLimitError`。
- `500`：抛出 `ProviderServerError`。
- `connection_error`：抛出 `ProviderConnectionError`。
- `invalid_response`：抛出 `ProviderInvalidResponseError`。
- `slow_response`：使用 `asyncio.sleep` 产生可配置的确定性延迟后返回正常响应。

Mock 不使用随机故障；随机故障注入属于后续 Reliability 阶段。请求 ID 使用可注入工厂生成，以便测试确定性行为。

## OpenAICompatibleProvider

该 Provider 负责共享的 OpenAI-compatible HTTP 协议：

1. 将 `ChatRequest` 转换为 `POST {base_url}/chat/completions` 的 JSON。
2. 使用 Bearer API Key 发起异步 HTTP 请求。
3. 将 `choices[0].message.content`、`id`、`model` 和 usage 映射到 `ChatResponse`。
4. 将 HTTP 状态、超时、连接错误及非法响应映射为统一异常。

构造函数接收 `base_url`、`api_key`、`provider_name`、timeout，以及可选的外部 `httpx.AsyncClient`。测试注入客户端或 `MockTransport`，不启动真实网络服务。

客户端所有权必须明确：由 Provider 内部创建的客户端通过 `async with` 或 `aclose()` 关闭；外部注入的客户端由调用方管理，Provider 不得擅自关闭。

## ZhipuProvider

`ZhipuProvider` 是薄适配器，通过组合复用 `OpenAICompatibleProvider`：

- 固定内部 provider 名称为 `zhipu`。
- 从显式构造参数接收 API Key、base URL 和 timeout。
- 缺少 API Key 或 base URL 时，在构造阶段抛出 `ProviderConfigurationError`。
- `chat()` 委托兼容协议层，并保证响应的 provider 字段为 `zhipu`。

Phase 1 不引入智谱官方 SDK，避免形成第二套响应和异常体系。

## 配置

扩展 `Settings`：

- `zhipu_api_key: str | None = None`
- `zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"`
- `zhipu_chat_model: str = "glm-4-flash"`
- `provider_timeout_seconds: float`，必须大于 0

应用和 Phase 0 测试在没有 Key 时仍可启动。只有构造真实 `ZhipuProvider` 时要求 Key。

## 数据流

```text
Business code
  -> BaseProvider.chat(ChatRequest)
  -> MockProvider
     or ZhipuProvider -> OpenAICompatibleProvider -> HTTPX
  -> ChatResponse or ProviderError
```

不存在 Router 或隐式 Provider 切换；调用方显式获得一个 Provider 实例。Phase 2 再增加 Registry 与 Router。

## 测试策略

严格按 TDD 实施：每个行为先写失败测试，确认失败原因正确，再加入最小实现。

必须覆盖：

1. Schema 对合法输入的解析，以及空 model、空 messages、非法 role、负 usage 的拒绝。
2. MockProvider 的 normal、timeout、429、500、connection_error、invalid_response、slow_response 和未知模式。
3. OpenAI-compatible 请求 URL、Bearer header、JSON body 和统一响应映射。
4. HTTP 200 非法 JSON、字段缺失、401、403、429、其他 4xx、500、ReadTimeout 和 ConnectError 的异常映射。
5. 外部注入客户端不会被 Provider 关闭，内部客户端能够关闭。
6. ZhipuProvider 的配置校验、委托行为和 provider 名称。
7. 同一个只依赖 `BaseProvider` 的业务函数可分别消费 Mock、OpenAI-compatible 和 Zhipu 响应。
8. 现有 Phase 0 测试继续通过。

真实智谱 E2E 单独标记，默认测试命令不得触发网络调用。

## 验收标准

- `python -m pytest -v` 全部通过且没有真实网络调用。
- `python -m compileall -q app` 成功。
- 所有 Provider 返回 `ChatResponse` 或抛出 `ProviderError` 子类。
- Debug Drill 中的非法 JSON、401、429、500、ReadTimeout 和 ConnectionError 均有自动化测试。
- 同一业务代码仅替换 Provider 实例即可运行。
- 没有 API Key 被 Git 跟踪，Phase 0 的 `/health` 仍返回 200 与 `{"status":"ok"}`。
