# Phase 1 Unified Provider SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tested Mock, OpenAI-compatible, and Zhipu providers behind one asynchronous request, response, and exception contract.

**Architecture:** Pydantic models define the boundary consumed by business code. `OpenAICompatibleProvider` owns HTTP transport and normalization; `ZhipuProvider` composes that implementation with Zhipu defaults, while `MockProvider` supplies deterministic success and failure behavior without network access.

**Tech Stack:** Python 3.11+, Pydantic 2, HTTPX 0.28.1, pytest 8.4.1, asyncio

**Spec:** `docs/superpowers/specs/2026-09-15-phase-1-provider-sdk-design.md`

## Global Constraints

- Unit and protocol integration tests must not access the internet or spend model tokens.
- Do not implement Router, Retry, Fallback, Circuit Breaker, streaming, or load testing.
- All providers return `ChatResponse` or raise a `ProviderError` subclass; HTTPX exceptions never cross the provider boundary.
- API keys come only from constructor arguments backed by environment configuration and must not appear in logs, exceptions, fixtures, or Git.
- Phase 0 must continue to start without a Zhipu API key and `/health` must remain unchanged.
- Add concise Chinese comments or docstrings at public contracts, exception-mapping decisions, client-ownership rules, and non-obvious logic. Do not comment self-explanatory assignments or repeat the code in Chinese.
- Follow red-green-refactor: every production behavior is preceded by a focused failing test and an observed expected failure.

## File Map

- Create `app/providers/__init__.py`: export the public provider contract.
- Modify `app/providers/schemas.py`: validate unified request, response, and token usage models.
- Modify `app/providers/errors.py`: define safe typed provider exceptions.
- Modify `app/providers/base.py`: document the async provider interface.
- Replace `app/providers/mock.py`: implement deterministic mock modes.
- Replace `app/providers/openai_compatible.py`: implement shared HTTP protocol and exception mapping.
- Replace `app/providers/zhipu.py`: compose the compatible provider with Zhipu identity.
- Modify `app/config.py`: add optional Zhipu settings and a positive provider timeout.
- Modify `.env.example`: document Phase 1 values without secrets.
- Create `tests/providers/__init__.py`: mark the provider test package.
- Create `tests/providers/test_schemas.py`: cover boundary validation.
- Create `tests/providers/test_mock.py`: cover all deterministic mock modes.
- Create `tests/providers/test_openai_compatible.py`: cover request mapping, response mapping, errors, and client ownership.
- Create `tests/providers/test_zhipu.py`: cover Zhipu configuration and delegation.
- Create `tests/providers/test_contract.py`: prove business-code substitutability.

---

### Task 1: Unified schemas, exceptions, and configuration

**Files:**
- Create: `app/providers/__init__.py`
- Modify: `app/providers/base.py`
- Modify: `app/providers/schemas.py`
- Modify: `app/providers/errors.py`
- Modify: `app/config.py`
- Modify: `.env.example`
- Create: `tests/providers/__init__.py`
- Create: `tests/providers/test_schemas.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `ChatMessage`, `ChatRequest`, `TokenUsage`, `ChatResponse`, `BaseProvider.chat(request: ChatRequest) -> ChatResponse`, and the complete `ProviderError` hierarchy.
- Produces: `Settings.zhipu_api_key`, `zhipu_base_url`, `zhipu_chat_model`, and `provider_timeout_seconds`.

- [ ] **Step 1: Write failing schema validation tests**

Create `tests/providers/__init__.py` and `tests/providers/test_schemas.py` with literal expectations:

```python
import pytest
from pydantic import ValidationError

from app.providers.schemas import ChatMessage, ChatRequest, ChatResponse, TokenUsage


def test_chat_response_preserves_the_unified_contract() -> None:
    response = ChatResponse(
        request_id="req_1",
        provider="mock",
        model="mock-v1",
        content="hello",
        latency_ms=1.5,
        usage=TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    assert response.model_dump() == {
        "request_id": "req_1", "provider": "mock", "model": "mock-v1",
        "content": "hello", "latency_ms": 1.5,
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }


@pytest.mark.parametrize(
    "request",
    [
        {"model": "", "messages": [{"role": "user", "content": "hello"}]},
        {"model": "mock-v1", "messages": []},
        {"model": "mock-v1", "messages": [{"role": "tool", "content": "hello"}]},
        {"model": "mock-v1", "messages": [{"role": "user", "content": ""}]},
    ],
)
def test_chat_request_rejects_invalid_boundary_values(request: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(request)


def test_token_usage_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(prompt_tokens=-1)
```

- [ ] **Step 2: Verify the schema tests fail for missing validation**

Run: `.\.venv\Scripts\python -m pytest tests/providers/test_schemas.py -v`

Expected: parametrized invalid request and negative usage cases fail because the current models accept them.

- [ ] **Step 3: Implement the validated contract and safe exceptions**

Use `Literal["system", "user", "assistant"]`, `Field(min_length=1)`, `Field(min_length=1)` on the message list, and `Field(default=0, ge=0)` on token counts. Add Chinese class docstrings explaining that these models isolate business code from provider payloads. Add `ProviderConfigurationError` and `ProviderRequestError` to `errors.py`; give `ProviderError` safe `provider` and optional `status_code` fields without storing response bodies or headers. Keep the abstract signature fully typed and add a Chinese docstring describing the provider boundary.

- [ ] **Step 4: Add failing Phase 1 settings tests**

Extend `SETTINGS_ENV_VARS` with `ZHIPU_API_KEY`, `ZHIPU_BASE_URL`, `ZHIPU_CHAT_MODEL`, and `PROVIDER_TIMEOUT_SECONDS`. Assert safe defaults, environment overrides, and rejection of timeout values `0`, `-1`, and `not-a-number`.

- [ ] **Step 5: Verify the settings tests fail, then implement the settings**

Run: `.\.venv\Scripts\python -m pytest tests/test_config.py -v`

Implement:

```python
zhipu_api_key: str | None = None
zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
zhipu_chat_model: str = "glm-4-flash"
provider_timeout_seconds: float = Field(default=30.0, gt=0)
```

Add the same names to `.env.example` with `ZHIPU_API_KEY=` and safe non-secret defaults. Re-run both test files and expect all tests to pass.

- [ ] **Step 6: Export and commit the contract**

Export the schemas, exceptions, and `BaseProvider` from `app/providers/__init__.py`, then run:

```powershell
.\.venv\Scripts\python -m pytest tests/providers/test_schemas.py tests/test_config.py -v
git add -- app/providers/__init__.py app/providers/base.py app/providers/schemas.py app/providers/errors.py app/config.py .env.example tests/providers/__init__.py tests/providers/test_schemas.py tests/test_config.py
git commit -m "feat: define unified provider contract"
```

### Task 2: Deterministic MockProvider

**Files:**
- Replace: `app/providers/mock.py`
- Create: `tests/providers/test_mock.py`

**Interfaces:**
- Consumes: `ChatRequest`, `ChatResponse`, `TokenUsage`, and unified exceptions from Task 1.
- Produces: `MockProvider(mode: MockMode = "normal", slow_delay_seconds: float = 0.01, request_id_factory: Callable[[], str] = default_request_id)` where `default_request_id()` returns `f"req_{uuid4().hex}"`.

- [ ] **Step 1: Write failing normal and invalid-mode tests**

Create async tests using `asyncio.run()` so no async pytest plugin is needed. Assert that normal mode returns a `ChatResponse` with provider `mock`, the requested model, content `mock response`, injected request ID, non-negative latency, and zero usage. Assert constructor mode `typo` raises `ProviderConfigurationError`.

- [ ] **Step 2: Run the focused tests and observe the contract failure**

Run: `.\.venv\Scripts\python -m pytest tests/providers/test_mock.py -v`

Expected: normal mode fails because the current implementation returns a string; invalid mode fails because the constructor accepts it.

- [ ] **Step 3: Implement normal mode and validated modes**

Define:

```python
MockMode = Literal["normal", "timeout", "429", "500", "connection_error", "invalid_response", "slow_response"]
```

Validate against `get_args(MockMode)` during construction. Use `time.perf_counter()` for latency and an injected `request_id_factory`. Add a Chinese comment explaining why deterministic modes are used instead of random failures.

- [ ] **Step 4: Add and verify each failure-mode test one at a time**

For `timeout`, `429`, `500`, `connection_error`, and `invalid_response`, assert the exact unified exception class. For `slow_response`, inject `0.01`, assert a valid response, and assert elapsed time is at least `0.008` seconds without requiring an exact scheduler duration. Run the focused test after adding each case and observe it fail before implementing that branch.

- [ ] **Step 5: Replace the branch chain with a typed mapping and commit**

Use a mode-to-exception-class mapping for immediate failures and explicit branches only for normal and delayed success. Remove the demonstration `main()`. Run:

```powershell
.\.venv\Scripts\python -m pytest tests/providers/test_mock.py -v
git add -- app/providers/mock.py tests/providers/test_mock.py
git commit -m "feat: add deterministic mock provider"
```

### Task 3: OpenAI-compatible HTTP provider

**Files:**
- Replace: `app/providers/openai_compatible.py`
- Create: `tests/providers/test_openai_compatible.py`

**Interfaces:**
- Consumes: Task 1 contracts and `httpx.AsyncClient`.
- Produces: `OpenAICompatibleProvider(base_url: str, api_key: str, provider_name: str = "openai-compatible", timeout_seconds: float = 30.0, client: httpx.AsyncClient | None = None)` with `chat()` and `aclose()`.

- [ ] **Step 1: Write the failing request/response mapping test**

Use `httpx.MockTransport` with an async handler. Capture the request and return literal JSON containing `id`, `model`, `choices[0].message.content`, and usage. Assert URL `/chat/completions`, method POST, `Authorization: Bearer test-key`, request JSON, and the complete `ChatResponse`.

- [ ] **Step 2: Verify RED, then implement successful mapping**

Run: `.\.venv\Scripts\python -m pytest tests/providers/test_openai_compatible.py::test_maps_request_and_response -v`

Implement constructor validation, payload creation, elapsed-time measurement, and response parsing. Add Chinese comments at the normalization boundary rather than on obvious HTTPX calls.

- [ ] **Step 3: Add failing status-code mapping tests**

Parametrize literal pairs:

```python
[(401, ProviderAuthenticationError), (403, ProviderAuthenticationError),
 (429, ProviderRateLimitError), (400, ProviderRequestError),
 (500, ProviderServerError), (503, ProviderServerError)]
```

Assert every raised exception is a `ProviderError`, records provider and status code, and excludes `test-key` from `str(error)`.

- [ ] **Step 4: Implement status mapping and verify GREEN**

Map status codes before JSON parsing. Add a Chinese comment explaining why authentication, throttling, request, and server failures remain distinct for later reliability policy. Do not call `response.raise_for_status()` without translating its exception.

- [ ] **Step 5: Add transport and invalid-response tests, then implement them**

Use custom `httpx.AsyncBaseTransport` test doubles that raise `httpx.ReadTimeout` and `httpx.ConnectError`. Add responses for invalid JSON, empty `choices`, and missing content. Observe each test fail, then translate them to `ProviderTimeoutError`, `ProviderConnectionError`, and `ProviderInvalidResponseError` respectively.

- [ ] **Step 6: Test and implement client ownership**

Verify `aclose()` does not close an injected client. Patch or inject a client factory for the internally owned case and verify the provider closes that client. Store `_owns_client = client is None`; add a Chinese comment explaining that callers retain ownership of injected resources.

- [ ] **Step 7: Run focused and full tests, then commit**

```powershell
.\.venv\Scripts\python -m pytest tests/providers/test_openai_compatible.py -v
.\.venv\Scripts\python -m pytest -v
git add -- app/providers/openai_compatible.py tests/providers/test_openai_compatible.py
git commit -m "feat: add openai compatible provider"
```

### Task 4: Zhipu adapter and provider substitutability

**Files:**
- Replace: `app/providers/zhipu.py`
- Create: `tests/providers/test_zhipu.py`
- Create: `tests/providers/test_contract.py`
- Modify: `app/providers/__init__.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `OpenAICompatibleProvider` and Task 1 contracts.
- Produces: `ZhipuProvider(api_key: str, base_url: str = "https://open.bigmodel.cn/api/paas/v4", timeout_seconds: float = 30.0, client: httpx.AsyncClient | None = None)`.

- [ ] **Step 1: Write failing Zhipu configuration and delegation tests**

Assert empty API key and empty base URL raise `ProviderConfigurationError`. With an injected `MockTransport`, assert `chat()` posts to the Zhipu-compatible endpoint and returns provider `zhipu`. Verify `aclose()` follows the compatible provider's ownership semantics.

- [ ] **Step 2: Verify RED, then implement thin composition**

Run: `.\.venv\Scripts\python -m pytest tests/providers/test_zhipu.py -v`

Store one private `OpenAICompatibleProvider(provider_name="zhipu", ...)`; delegate `chat()` and `aclose()`. Add a Chinese class docstring explaining that composition prevents a second HTTP and exception stack.

- [ ] **Step 3: Write the cross-provider contract test**

Define one test-only business function:

```python
async def get_content(provider: BaseProvider, request: ChatRequest) -> str:
    response = await provider.chat(request)
    return response.content
```

Run it unchanged against `MockProvider`, an `OpenAICompatibleProvider` backed by `MockTransport`, and `ZhipuProvider` backed by `MockTransport`. Assert all return their literal content strings.

- [ ] **Step 4: Export providers and document Phase 1**

Export `MockProvider`, `OpenAICompatibleProvider`, and `ZhipuProvider` from `app/providers/__init__.py`. Update README with the unified request example, supported deterministic mock modes, the rule that normal tests never call real APIs, and the fact that Router/reliability behavior begins in later phases.

- [ ] **Step 5: Run final acceptance checks**

```powershell
.\.venv\Scripts\python -m pytest -v
.\.venv\Scripts\python -m compileall -q app
.\.venv\Scripts\python -c "from app.providers import MockProvider, OpenAICompatibleProvider, ZhipuProvider; print('provider imports ok')"
git check-ignore -v .env .venv
git ls-files --error-unmatch .env
```

Expected: all tests pass; compilation and imports succeed; `.env` and `.venv` are ignored; `git ls-files --error-unmatch .env` exits 1.

- [ ] **Step 6: Commit the Phase 1 integration**

```powershell
git add -- app/providers/__init__.py app/providers/zhipu.py tests/providers/test_zhipu.py tests/providers/test_contract.py README.md
git commit -m "feat: complete unified provider sdk"
```
