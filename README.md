# LLM Gateway Lab

面向 FDE 学习与实践的、可靠性导向的多供应商 LLM 网关。

当前已完成 Phase 2 Model Registry 与 Router：在 Phase 1 统一 Provider SDK 基础上，支持 Provider/模型注册、YAML 路由配置、候选排序和最高优先级模型的单次调用。Phase 0 的健康检查保持不变。

## 环境要求

- Python 3.11+
- Git
- Windows PowerShell

## 初始化

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如果系统的 `python` 命令不可用，但已安装 Conda，可使用以下命令创建虚拟环境：

```powershell
conda run -n base python -m venv .venv
```

## 运行测试

```powershell
.\.venv\Scripts\python -m pytest -v
```

常规测试全部使用确定性 Mock 或 `httpx.MockTransport`，不会调用真实 API，也不会产生模型费用。

## 统一 Provider 用法

业务函数只依赖 `BaseProvider`，切换实现时无需修改 `ChatRequest` 或响应处理：

```python
import asyncio

from app.providers import BaseProvider, ChatMessage, ChatRequest, MockProvider


async def get_content(provider: BaseProvider, request: ChatRequest) -> str:
    response = await provider.chat(request)
    return response.content


request = ChatRequest(
    model="demo-model",
    messages=[ChatMessage(role="user", content="你好")],
)
content = asyncio.run(get_content(MockProvider(), request))
```

`MockProvider` 提供七种可重复的测试模式：

- `normal`：立即返回规范化成功响应。
- `timeout`：抛出统一超时异常。
- `429`：抛出统一限流异常。
- `500`：抛出统一服务端异常。
- `connection_error`：抛出统一连接异常。
- `invalid_response`：抛出统一无效响应异常。
- `slow_response`：延迟后返回成功响应，延迟值可配置。

## Router 用法

以下示例只使用 Mock，无需网络或密钥，通过公开 API 构建注册表和路由配置：

```python
import asyncio

from app.providers import ChatMessage, ChatRequest, MockProvider
from app.router import (
    CapabilityConfig, ModelRegistration, ModelRegistry, ModelRouter,
    ProviderRegistry, RouteConfig, RouterConfig,
)

providers = ProviderRegistry()
providers.register("mock", MockProvider())
models = ModelRegistry()
models.register(ModelRegistration(provider="mock", model="mock-primary"))
config = RouterConfig(capabilities={
    "text_generation": CapabilityConfig(routes=[
        RouteConfig(
            channel="primary", provider="mock", model="mock-primary", priority=1,
        ),
    ]),
})
router = ModelRouter(config, providers, models)
request = ChatRequest(
    model="business-placeholder",
    messages=[ChatMessage(role="user", content="你好")],
)
response = asyncio.run(router.route("text_generation", request))
print(response.content)
```

也可用 `load_router_config(Path("configs/models.yaml"))` 加载 YAML 配置（`Path` 来自 `pathlib`，加载函数来自 `app.router`）。候选按正整数 `priority` 升序排列，同优先级保持配置顺序，禁用的路由或模型会被过滤。`route()` 使用所选模型复制请求，调用一次最高优先级候选；Provider 异常直接传播。Retry、Fallback 与熔断尚未实现。

## 启动服务

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

启动后访问：

- 健康检查：http://127.0.0.1:8000/health
- Swagger：http://127.0.0.1:8000/docs

健康检查响应：

```json
{"status":"ok"}
```

## 配置

配置统一定义在 `app/config.py`，本地值放在 `.env`。`.env` 已被 Git 忽略，不要在代码、README、日志或提交历史中保存真实 API Key。

智谱相关变量已在 `.env.example` 中预留。使用真实 Provider 时由调用方读取并注入密钥；不要在代码、README、日志、异常或提交历史中保存真实 API Key。

## 常见问题

- `python` 不存在：安装 Python 3.11+，并在安装时启用 Add Python to PATH；已有 Conda 时也可使用上面的 Conda 命令。
- 无法运行激活脚本：无需激活虚拟环境，直接使用 `.\.venv\Scripts\python`。
- 端口 8000 被占用：启动命令追加 `--port 8001`，并访问对应端口。
- 配置加载失败：核对 `.env` 中的变量名和值；`APP_ENV` 只接受 `local`、`test` 或 `production`，`PORT` 必须在 1–65535 之间。
- 配置文件不存在：运行 `Copy-Item .env.example .env`；Phase 0 即使没有 `.env` 也能使用安全默认值启动。
- PowerShell 显示中文乱码：使用 `Get-Content -Encoding UTF8 <文件路径>`。
