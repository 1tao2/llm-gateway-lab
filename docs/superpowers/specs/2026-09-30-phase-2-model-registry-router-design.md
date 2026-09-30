# Phase 2 Model Registry 与 Router 设计

## 目标

建立由配置驱动的模型注册和路由层，将业务能力、模型名称与 Provider 解耦。业务代码只提供 `capability` 和统一的 `ChatRequest`，无需写针对具体模型的 `if/elif`。

Phase 2 只负责注册、校验、候选排序和单次调用。Retry、失败后自动 Fallback、Circuit Breaker、负载均衡和热加载不在本阶段实现。

## 核心边界

- `ProviderRegistry` 保存 `provider_name -> BaseProvider`，只管理已构造的 Provider 实例。
- `ModelRegistry` 使用 `(provider_name, model_name)` 复合键保存模型注册信息，因此不同 Provider 可以注册同名模型。
- `ModelRouter` 根据 capability 生成按优先级排序的有效候选，并可对第一个候选执行一次调用。
- YAML 只描述非敏感路由元数据，不保存 API Key；Provider 实例仍由 Python 代码结合环境变量构造。
- Provider 调用仍遵守 Phase 1 的 `BaseProvider`、`ChatRequest`、`ChatResponse` 和 `ProviderError` 契约。

## 模块结构

```text
app/router/
├── __init__.py
├── schemas.py
├── errors.py
├── registry.py
├── config.py
└── router.py

configs/
└── models.yaml

tests/router/
├── __init__.py
├── test_registry.py
├── test_config.py
└── test_router.py
```

## 数据模型

`ModelRegistration` 描述一个已经注册的模型：

- `provider: str`：非空 Provider 名称。
- `model: str`：非空模型名称。
- `enabled: bool = True`：模型级启用开关。

`RouteConfig` 描述 capability 下的一条配置路由：

- `channel: str`：例如 `primary` 或 `backup`，非空但不参与排序。
- `provider: str`：目标 Provider 名称。
- `model: str`：目标模型名称。
- `priority: int`：正整数，值越小优先级越高。
- `enabled: bool = True`：路由级启用开关。

`CapabilityConfig` 包含至少一条 `routes`。`RouterConfig` 保存 `capabilities: dict[str, CapabilityConfig]`，capability 名称不得为空。

`RouteCandidate` 是 Router 返回的已解析候选，包含原始路由字段以及实际的 `BaseProvider` 实例。它是不可变的运行时对象，调用方不能通过它修改注册表。

## 注册表

`ProviderRegistry.register(name, provider)` 注册实例；空名称、重复名称被拒绝。`get(name)` 在缺失时抛出 `ProviderNotRegisteredError`。

`ModelRegistry.register(registration)` 以 `(provider, model)` 注册模型；重复复合键被拒绝。`get(provider, model)` 在缺失时抛出 `ModelNotRegisteredError`。

注册表不读取 YAML，也不创建 Provider。这样新增 Provider 时只需实现 Phase 1 接口并在应用装配处注册，无须修改 Router 核心。

## 配置加载

`load_router_config(path: Path) -> RouterConfig` 使用 `yaml.safe_load` 读取 YAML，并交给 Pydantic 做结构和字段验证。文件不存在、YAML 语法错误或结构不合法时统一抛出 `RouterConfigurationError`，异常消息不得包含密钥等敏感值。

示例配置：

```yaml
capabilities:
  text_generation:
    routes:
      - channel: primary
        provider: mock
        model: mock-primary
        priority: 1
        enabled: true
      - channel: backup
        provider: zhipu
        model: glm-4-flash
        priority: 2
        enabled: true
```

首个示例默认只启用不需要密钥的 Mock 路由，避免导入配置或运行测试时产生真实网络调用。

## 路由行为

`ModelRouter.candidates(capability) -> tuple[RouteCandidate, ...]` 按以下顺序工作：

1. 查找 capability；不存在则抛出 `CapabilityNotFoundError`。
2. 过滤 `RouteConfig.enabled == false` 的路由。
3. 对每条剩余路由解析 Provider 与模型注册。
4. 过滤 `ModelRegistration.enabled == false` 的模型。
5. 按 `(priority, 配置中的原始顺序)` 稳定排序。
6. 没有候选时抛出 `NoEnabledRouteError`，否则返回不可变元组。

配置中启用但 Provider 或模型未注册属于配置错误，必须立即抛出对应异常，不能静默跳过并选择 backup。这样可以及时暴露 primary 拼写错误或装配遗漏。

`await ModelRouter.route(capability, request) -> ChatResponse` 获取候选列表，只选择第一个候选，将请求中的 `model` 替换为候选模型后调用一次 `candidate.provider.chat()`。调用方传入的请求对象不被原地修改。

首次 Provider 调用失败时，原始 `ProviderError` 直接向上传递，不自动尝试下一候选。Phase 3 将基于 `candidates()` 实现可观测的 Retry 与 Fallback 策略。

## 错误体系

所有路由层错误继承 `RouterError`：

- `RouterConfigurationError`：配置文件、YAML 或 Pydantic 校验失败。
- `DuplicateProviderError`：Provider 名称重复。
- `ProviderNotRegisteredError`：路由引用了未注册 Provider。
- `DuplicateModelError`：相同 `(provider, model)` 重复注册。
- `ModelNotRegisteredError`：路由引用了未注册模型。
- `CapabilityNotFoundError`：请求了不存在的 capability。
- `NoEnabledRouteError`：capability 存在但无可用路由。

这些错误只表达 Router/Registry 问题。Provider 调用错误继续使用 Phase 1 的 `ProviderError` 子类。

## 测试策略

严格按 TDD 实施，测试不得访问互联网或消耗真实 API：

1. Provider 注册、查找、重复注册和缺失查找。
2. 模型复合键、同名模型跨 Provider 共存、重复注册和缺失查找。
3. YAML 正常加载，以及文件缺失、语法错误、字段非法的安全异常。
4. capability 缺失、全部路由禁用、模型禁用。
5. priority 排序及相同 priority 时保持配置顺序。
6. primary 禁用后 backup 成为首选。
7. 启用路由引用未知 Provider 或模型时立即报错。
8. `route()` 使用候选模型构造新请求、只调用首选一次并返回统一响应。
9. 首选抛出 `ProviderError` 时不调用 backup。
10. Phase 0、Phase 1 现有测试继续通过。

## 验收标准

- 新增 Provider 不需要修改 Router 核心代码。
- 主备顺序完全由配置的 `enabled` 和 `priority` 决定。
- 禁用 primary 后，backup 成为第一个有效候选。
- 不同 Provider 下相同 `model_name` 能被正确区分。
- 错误配置产生明确、稳定且不泄露敏感信息的 Router 异常。
- `route()` 只执行一次 Provider 调用，不包含 Retry 或自动 Fallback。
- `python -m pytest -v` 全部通过且不进行真实网络调用。
- `python -m compileall -q app` 成功。
