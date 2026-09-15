# Phase 0：项目骨架与工程基线设计

## 背景

`llm-gateway-lab` 当前已有 Git 仓库、README、`.gitignore` 和学习手册，但尚无 Python 应用代码。Phase 0 的目标是建立能够持续迭代的最小工程基线，不提前实现 Provider、Router、Reliability、RAG 或 Agent。

项目在 Windows 环境开发，使用 Python 3.11+、`venv + pip + requirements.txt` 管理运行环境和依赖。

## 目标

- 建立可导入、可启动、可测试的 FastAPI 应用。
- 提供 `GET /health` 健康检查。
- 使用统一配置对象读取环境变量。
- 确保真实 `.env` 和密钥不会进入 Git。
- 让另一台 Windows 电脑能够仅根据 README 完成初始化。
- 对健康检查和配置行为提供自动化测试。

## 非目标

- 不接入智谱或其他真实模型。
- 不创建 Provider、Router、Reliability、Observability、RAG 或 Agent 模块。
- 不引入 Docker；Docker 在 Phase 9 实现。
- 不加入数据库、Redis、消息队列或前端。
- 不要求 Phase 0 提供任何 API Key。

## 目录结构

```text
llm-gateway-lab/
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── config.py
├── configs/
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   └── test_health.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

这里只创建 Phase 0 有实际职责的 Python 模块。后续目录由对应 Phase 引入，避免空架构和无效占位文件。

## 组件设计

### `app/config.py`

定义唯一的配置入口 `Settings`。配置来自环境变量，并提供适合本地开发的非敏感默认值，例如应用名称、运行环境、主机和端口。

约束：

- Phase 0 不把 `ZHIPU_API_KEY` 设为必填项。
- 数值、枚举等非法配置必须在加载时给出明确的验证错误。
- 业务模块不得直接散落调用 `os.getenv()`。
- 测试必须能够创建隔离的配置实例，不能依赖开发者机器的环境状态。

### `app/main.py`

创建 FastAPI 应用并注册 `GET /health`。

响应固定为：

```json
{
  "status": "ok"
}
```

Phase 0 的健康检查仅表达进程存活和 HTTP 服务可用，不谎称数据库、模型或外部依赖健康。

### 测试

`test_health.py` 使用 FastAPI `TestClient` 调用应用，不绑定真实端口，验证：

- `/health` 返回 HTTP 200。
- 响应体严格等于约定 Schema。

`test_config.py` 验证：

- 没有 `.env` 和智谱密钥时可以使用安全默认值。
- 环境变量能够覆盖默认值。
- 非法配置会被拒绝并产生清晰错误。

## 依赖管理

使用 `requirements.txt`，只加入 Phase 0 必需依赖：

- FastAPI
- Uvicorn
- Pydantic Settings
- python-dotenv（由配置加载使用）
- pytest
- HTTPX（FastAPI TestClient 依赖及后续阶段复用）

依赖应固定到经过验证的具体版本，确保另一台机器可以复现。升级依赖时通过测试后再修改版本。

## 密钥与 Git 安全

`.env.example` 仅包含空值或安全示例值，并预留：

```text
ZHIPU_API_KEY=
ZHIPU_BASE_URL=
ZHIPU_CHAT_MODEL=
ZHIPU_EMBEDDING_MODEL=
```

`.gitignore` 必须忽略：

- `.env` 及本地环境文件，但保留 `.env.example`。
- `.venv/`。
- Python 缓存、pytest 缓存、覆盖率文件。
- IDE 和操作系统产生的本地文件。

验收时使用 Git 检查确认 `.env` 和 `.venv` 不会被跟踪。

## README 启动流程

README 至少提供以下 Windows PowerShell 流程：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

同时说明访问 `http://127.0.0.1:8000/health` 和 `http://127.0.0.1:8000/docs`。

## 错误处理

- 配置加载失败时应在启动阶段快速失败，并保留具体字段的验证信息。
- `/health` 不捕获或伪装启动错误。
- 测试失败必须返回非零退出码。
- README 包含端口占用、虚拟环境未激活和 UTF-8 读取问题的最小排查提示。

## 验收标准

在全新虚拟环境中执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest
```

必须全部成功，并进一步验证：

- `python -m uvicorn app.main:app` 能启动。
- `GET /health` 返回 200 和 `{"status":"ok"}`。
- 无智谱密钥时仍可启动 Phase 0。
- 非法配置测试能够证明验证逻辑生效。
- `git status --ignored` 证明 `.env`、`.venv` 和缓存文件已被忽略。
- README 的初始化命令与实际项目一致。

## 后续扩展边界

Phase 1 将新增 `app/providers/`，并在不修改 `/health` 契约的前提下接入 MockProvider、ZhipuProvider 和兼容协议测试服务。Phase 0 不为这些模块创建空实现。
