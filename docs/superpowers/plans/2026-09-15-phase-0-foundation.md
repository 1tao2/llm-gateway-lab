# Phase 0 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, testable FastAPI foundation with centralized configuration, a health endpoint, safe environment handling, and Windows setup documentation.

**Architecture:** Keep Phase 0 deliberately small: `app.config` owns validated environment configuration, while `app.main` owns the FastAPI application and health contract. Tests instantiate configuration and call the ASGI application without opening a network port; later phases add modules without changing these boundaries.

**Tech Stack:** Python 3.11+, venv, pip, FastAPI 0.116.1, Uvicorn 0.35.0, Pydantic Settings 2.10.1, HTTPX 0.28.1, pytest 8.4.1

**Spec:** `docs/superpowers/specs/2026-09-15-phase-0-foundation-design.md`

## Global Constraints

- Use Python 3.11 or newer on Windows.
- Manage the environment with `venv + pip + requirements.txt`.
- Phase 0 must start without a Zhipu API key.
- Do not create Provider, Router, Reliability, Observability, RAG, Agent, Docker, database, Redis, queue, or frontend implementations.
- Application modules must not scatter direct `os.getenv()` calls; configuration belongs in `app.config.Settings`.
- `.env`, `.venv`, caches, credentials, and machine-local state must not be committed.
- Use tests before implementation and commit each independently testable deliverable.

## File Map

- Create `app/__init__.py`: marks the application package.
- Create `app/config.py`: defines validated `Settings` and cached `get_settings()`.
- Create `app/main.py`: constructs FastAPI and exposes `GET /health`.
- Create `tests/__init__.py`: marks the test package.
- Create `tests/test_config.py`: verifies defaults, overrides, and invalid configuration.
- Create `tests/test_health.py`: verifies the health endpoint contract.
- Create `configs/.gitkeep`: preserves the future configuration directory.
- Create `.env.example`: documents safe local variables and future Zhipu variables.
- Create `requirements.txt`: pins the Phase 0 runtime and test dependencies.
- Modify `.gitignore`: preserves `.env.example` while ignoring local environment variants.
- Modify `README.md`: documents initialization, validation, startup, endpoints, and troubleshooting.

---

### Task 1: Validated application configuration

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: process environment variables and optional repository-root `.env`.
- Produces: `Settings(app_name: str, app_env: Literal["local", "test", "production"], host: str, port: int, log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])` and `get_settings() -> Settings`.

- [ ] **Step 1: Pin the Phase 0 dependencies**

Create `requirements.txt`:

```text
fastapi==0.116.1
httpx==0.28.1
pydantic-settings==2.10.1
pytest==8.4.1
uvicorn[standard]==0.35.0
```

- [ ] **Step 2: Create package markers and write the failing configuration tests**

Create empty `app/__init__.py` and `tests/__init__.py`, then create `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from app.config import Settings


SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_ENV",
    "HOST",
    "PORT",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_settings_use_safe_defaults_without_api_key() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "LLM Gateway Lab"
    assert settings.app_env == "local"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("port", ["0", "65536", "not-a-number"])
def test_invalid_port_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    monkeypatch.setenv("PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

- [ ] **Step 3: Create a virtual environment and install dependencies**

Run:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Expected: installation exits with code 0.

- [ ] **Step 4: Run the configuration tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_config.py -v
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 5: Implement the minimal validated configuration**

Create `app/config.py`:

```python
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LLM Gateway Lab"
    app_env: Literal["local", "test", "production"] = "local"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run the configuration tests and verify they pass**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_config.py -v
```

Expected: 5 tests pass.

- [ ] **Step 7: Commit the configuration deliverable**

```powershell
git add -- requirements.txt app/__init__.py app/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: establish validated application settings"
```

### Task 2: FastAPI application and health contract

**Files:**
- Create: `app/main.py`
- Create: `tests/test_health.py`

**Interfaces:**
- Consumes: `get_settings() -> Settings` from `app.config`.
- Produces: module-level `app: FastAPI` and `GET /health -> {"status": "ok"}`.

- [ ] **Step 1: Write the failing health endpoint tests**

Create `tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_documents_health_endpoint() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
```

- [ ] **Step 2: Run the health tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_health.py -v
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Implement the minimal FastAPI application**

Create `app/main.py`:

```python
from typing import Literal, TypedDict

from fastapi import FastAPI

from app.config import get_settings


class HealthResponse(TypedDict):
    status: Literal["ok"]


settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.get("/health", tags=["system"])
async def health() -> HealthResponse:
    return {"status": "ok"}
```

- [ ] **Step 4: Run the health and full test suites**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_health.py -v
.\.venv\Scripts\python -m pytest -v
```

Expected: 2 health tests pass; 7 tests pass in the full suite.

- [ ] **Step 5: Start the server and validate the real HTTP path**

Run in one terminal:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run in another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected: Uvicorn starts successfully and PowerShell displays `status : ok`. Stop Uvicorn with Ctrl+C.

- [ ] **Step 6: Commit the HTTP deliverable**

```powershell
git add -- app/main.py tests/test_health.py
git commit -m "feat: add application health endpoint"
```

### Task 3: Environment safety and reproducible documentation

**Files:**
- Create: `configs/.gitkeep`
- Create: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: the configuration fields and commands introduced in Tasks 1 and 2.
- Produces: a safe environment template and a complete Windows onboarding procedure.

- [ ] **Step 1: Create the environment example**

Create `.env.example`:

```dotenv
APP_NAME=LLM Gateway Lab
APP_ENV=local
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=INFO

# Phase 1 and later. Keep secrets out of Git.
ZHIPU_API_KEY=
ZHIPU_BASE_URL=
ZHIPU_CHAT_MODEL=
ZHIPU_EMBEDDING_MODEL=
```

Create an empty `configs/.gitkeep`.

- [ ] **Step 2: Strengthen environment ignore rules**

Add directly below the existing `# Environments` heading in `.gitignore`:

```gitignore
.env.*
!.env.example
```

Keep the existing `.env`, `.venv`, cache, and Python artifact rules.

- [ ] **Step 3: Verify secret and virtual-environment files are ignored**

Create temporary local files using PowerShell:

```powershell
New-Item -ItemType File -Force .env | Out-Null
New-Item -ItemType File -Force .env.local | Out-Null
git check-ignore -v .env .env.local .venv
git check-ignore .env.example
```

Expected: the first `git check-ignore` lists rules for all three ignored paths; `git check-ignore .env.example` produces no output and exits with code 1 because the example must remain trackable. Delete only the two temporary files:

```powershell
Remove-Item -LiteralPath .env,.env.local
```

- [ ] **Step 4: Replace README with verified onboarding instructions**

Replace `README.md` with:

````markdown
# LLM Gateway Lab

面向 FDE 学习与实践的、可靠性导向的多供应商 LLM 网关。

当前完成 Phase 0：FastAPI 工程骨架、统一配置、健康检查与自动化测试。此阶段不需要智谱 API Key，也不会产生模型调用费用。

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

## 运行测试

```powershell
.\.venv\Scripts\python -m pytest -v
```

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

智谱相关变量已在 `.env.example` 中预留，但 Phase 0 不读取或要求这些变量；它们将在 Phase 1 接入真实 Provider 时启用。

## 常见问题

- `python` 不存在：安装 Python 3.11+，并在安装时启用 Add Python to PATH。
- 无法运行激活脚本：无需激活虚拟环境，直接使用 `.\.venv\Scripts\python`。
- 端口 8000 被占用：追加 `--port 8001`，并访问对应端口。
- PowerShell 显示中文乱码：使用 `Get-Content -Encoding UTF8 <文件路径>`。
````

- [ ] **Step 5: Run the complete acceptance checks**

Run:

```powershell
.\.venv\Scripts\python -m pytest -v
.\.venv\Scripts\python -c "from app.config import Settings; print(Settings(_env_file=None).model_dump())"
.\.venv\Scripts\python -c "from app.main import app; print(app.title)"
git status --short --ignored
```

Expected: all 7 tests pass; both imports succeed; `.env`, `.venv`, and caches appear only as ignored entries; `.env.example` remains trackable.

- [ ] **Step 6: Commit the reproducibility deliverable**

```powershell
git add -- .env.example .gitignore README.md configs/.gitkeep
git commit -m "docs: add reproducible phase 0 setup"
```

### Task 4: Final Phase 0 verification

**Files:**
- Verify only; do not add implementation files unless a failed acceptance check identifies a concrete defect.

**Interfaces:**
- Consumes: all Phase 0 deliverables.
- Produces: evidence that the repository satisfies the Phase 0 acceptance criteria.

- [ ] **Step 1: Verify the complete test suite from the project root**

```powershell
.\.venv\Scripts\python -m pytest -v
```

Expected: 7 tests pass and 0 fail.

- [ ] **Step 2: Verify FastAPI startup without a Zhipu key**

Run Uvicorn with `ZHIPU_API_KEY` absent and request `/health`:

```powershell
Remove-Item Env:ZHIPU_API_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: startup succeeds; `GET /health` returns HTTP 200 and `{"status":"ok"}`. Stop Uvicorn with Ctrl+C.

- [ ] **Step 3: Verify repository safety and scope**

```powershell
git status --short --ignored
rg --files app tests configs
```

Expected: no `.env`, `.venv`, cache, or credential is staged; application files are limited to the Phase 0 file map; no Provider, Router, RAG, Agent, or Docker implementation exists.

- [ ] **Step 4: Record the verified result**

If Tasks 1–3 already produced their commits and every check above passes, do not create an empty commit. Record the exact test count, startup response, and Git safety result in the completion report.
