# LLM Gateway Lab

面向 FDE 学习与实践的、可靠性导向的多供应商 LLM 网关。

当前完成 Phase 1 Provider SDK：业务代码通过统一请求、响应和异常边界使用 Mock、OpenAI 兼容及智谱实现。Phase 0 的健康检查保持不变。

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

当前阶段仅提供单次非流式调用和供应商适配；Router 与重试、熔断等可靠性能力从后续阶段开始实现。

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
