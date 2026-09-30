# Phase 2 Model Registry and Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build configuration-driven Provider and model registries plus a Router that resolves ordered candidates and executes the highest-priority candidate once.

**Architecture:** Provider instances and model identities live in separate in-memory registries. Pydantic validates route metadata loaded through `yaml.safe_load`; `ModelRouter` resolves enabled routes into immutable candidates and keeps retry/fallback execution outside Phase 2.

**Tech Stack:** Python 3.11+, Pydantic 2, PyYAML 6, pytest, existing asynchronous Provider SDK

**Spec:** `docs/superpowers/specs/2026-09-30-phase-2-model-registry-router-design.md`

## Global Constraints

- API keys remain in environment settings and never appear in YAML, source, tests, logs, or Git.
- Unit tests must not access the internet or consume a real model API.
- Model identity is the composite `(provider, model)`, not `model` alone.
- Lower positive `priority` values run first; ties preserve YAML order.
- Enabled routes with missing registrations fail immediately instead of being silently skipped.
- `route()` performs exactly one Provider call and does not retry or automatically fall back.
- Existing Phase 0 `/health` and Phase 1 Provider contracts remain unchanged.

---

### Task 1: Route Configuration Schemas

**Files:**
- Modify: `requirements.txt`
- Create: `app/router/__init__.py`
- Create: `app/router/schemas.py`
- Create: `tests/router/__init__.py`
- Create: `tests/router/test_schemas.py`

**Interfaces:**
- Consumes: Pydantic `BaseModel`, `Field`, `ConfigDict`, and existing `BaseProvider`.
- Produces: `ModelRegistration`, `RouteConfig`, `CapabilityConfig`, `RouterConfig`, and immutable `RouteCandidate`.

- [ ] **Step 1: Add PyYAML dependency and write failing schema tests**

Add `PyYAML==6.0.2` to `requirements.txt`, then create tests that assert trimming, positive priority, non-empty route lists, and immutable candidates:

```python
from pydantic import ValidationError
import pytest

from app.providers import MockProvider
from app.router.schemas import (
    CapabilityConfig,
    ModelRegistration,
    RouteCandidate,
    RouteConfig,
    RouterConfig,
)


def test_route_models_validate_and_normalize_names() -> None:
    registration = ModelRegistration(provider=" mock ", model=" demo ")
    route = RouteConfig(
        channel=" primary ", provider=" mock ", model=" demo ", priority=1
    )
    config = RouterConfig(
        capabilities={" text_generation ": CapabilityConfig(routes=[route])}
    )

    assert registration.provider == "mock"
    assert registration.model == "demo"
    assert config.capabilities["text_generation"].routes[0].channel == "primary"


@pytest.mark.parametrize("priority", [0, -1])
def test_route_priority_must_be_positive(priority: int) -> None:
    with pytest.raises(ValidationError):
        RouteConfig(
            channel="primary", provider="mock", model="demo", priority=priority
        )


def test_capability_requires_at_least_one_route() -> None:
    with pytest.raises(ValidationError):
        CapabilityConfig(routes=[])


def test_route_candidate_is_immutable() -> None:
    candidate = RouteCandidate(
        channel="primary",
        provider_name="mock",
        model="demo",
        priority=1,
        provider=MockProvider(),
    )

    with pytest.raises(ValidationError):
        candidate.model = "changed"
```

- [ ] **Step 2: Run the schema tests and verify the expected import failure**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_schemas.py -v`

Expected: FAIL because `app.router.schemas` does not exist.

- [ ] **Step 3: Implement strict schemas with normalized non-empty names**

Use a shared `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` alias. Configure all Pydantic models with `extra="forbid"`; define `RouteCandidate` with `frozen=True` and `arbitrary_types_allowed=True`. Normalize capability dictionary keys in a `field_validator("capabilities", mode="before")`, rejecting blank and duplicate normalized keys.

- [ ] **Step 4: Run schema tests**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_schemas.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the schema slice**

```powershell
git add requirements.txt app/router/__init__.py app/router/schemas.py tests/router/__init__.py tests/router/test_schemas.py
git commit -m "feat: add phase 2 routing schemas"
```

---

### Task 2: Provider and Model Registries

**Files:**
- Create: `app/router/errors.py`
- Create: `app/router/registry.py`
- Create: `tests/router/test_registry.py`

**Interfaces:**
- Consumes: `BaseProvider` and `ModelRegistration`.
- Produces: `RouterError` subclasses, `ProviderRegistry.register/get`, and `ModelRegistry.register/get`.

- [ ] **Step 1: Write failing registry tests**

Cover successful lookup, duplicate rejection, missing lookup, and cross-provider model names:

```python
import pytest

from app.providers import MockProvider
from app.router.errors import (
    DuplicateModelError,
    DuplicateProviderError,
    ModelNotRegisteredError,
    ProviderNotRegisteredError,
)
from app.router.registry import ModelRegistry, ProviderRegistry
from app.router.schemas import ModelRegistration


def test_provider_registry_registers_and_resolves_instance() -> None:
    provider = MockProvider()
    registry = ProviderRegistry()
    registry.register("mock", provider)
    assert registry.get("mock") is provider


def test_provider_registry_rejects_duplicate_and_missing_names() -> None:
    registry = ProviderRegistry()
    registry.register("mock", MockProvider())
    with pytest.raises(DuplicateProviderError):
        registry.register("mock", MockProvider())
    with pytest.raises(ProviderNotRegisteredError):
        registry.get("missing")


def test_model_registry_uses_provider_and_model_as_composite_key() -> None:
    registry = ModelRegistry()
    first = ModelRegistration(provider="provider-a", model="same-name")
    second = ModelRegistration(provider="provider-b", model="same-name")
    registry.register(first)
    registry.register(second)
    assert registry.get("provider-a", "same-name") == first
    assert registry.get("provider-b", "same-name") == second


def test_model_registry_rejects_duplicate_and_missing_keys() -> None:
    registry = ModelRegistry()
    model = ModelRegistration(provider="mock", model="demo")
    registry.register(model)
    with pytest.raises(DuplicateModelError):
        registry.register(model)
    with pytest.raises(ModelNotRegisteredError):
        registry.get("mock", "missing")
```

- [ ] **Step 2: Run registry tests and verify failure**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_registry.py -v`

Expected: FAIL because registry modules do not exist.

- [ ] **Step 3: Implement errors and registries**

Define `RouterError(Exception)` and the seven subclasses named by the spec. Registries use private dictionaries, normalize lookup names with `.strip()`, reject blank names, and return the exact registered object. Exception messages include only safe Provider/model/capability identifiers.

- [ ] **Step 4: Run registry and schema tests**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_registry.py tests/router/test_schemas.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the registry slice**

```powershell
git add app/router/errors.py app/router/registry.py tests/router/test_registry.py
git commit -m "feat: add provider and model registries"
```

---

### Task 3: Safe YAML Configuration Loader

**Files:**
- Create: `app/router/config.py`
- Create: `tests/router/test_config.py`
- Create: `configs/models.yaml`

**Interfaces:**
- Consumes: filesystem `Path`, `yaml.safe_load`, and `RouterConfig.model_validate`.
- Produces: `load_router_config(path: Path) -> RouterConfig`.

- [ ] **Step 1: Install the pinned dependency**

Run: `.\.venv\Scripts\python -m pip install -r requirements.txt`

Expected: PyYAML 6.0.2 is installed successfully.

- [ ] **Step 2: Write failing loader tests**

Use `tmp_path` to cover a valid document, absent file, malformed YAML, and invalid schema. Assert failures are `RouterConfigurationError` and do not expose the document contents:

```python
from pathlib import Path

import pytest

from app.router.config import load_router_config
from app.router.errors import RouterConfigurationError


def test_load_router_config_parses_valid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        """capabilities:
  text_generation:
    routes:
      - channel: primary
        provider: mock
        model: mock-primary
        priority: 1
        enabled: true
""",
        encoding="utf-8",
    )
    config = load_router_config(path)
    assert config.capabilities["text_generation"].routes[0].model == "mock-primary"


@pytest.mark.parametrize(
    "contents", ["capabilities: [", "capabilities: {}", "secret-value"]
)
def test_load_router_config_maps_invalid_input_to_safe_error(
    tmp_path: Path, contents: str
) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(RouterConfigurationError) as captured:
        load_router_config(path)
    assert contents not in str(captured.value)


def test_load_router_config_maps_missing_file_to_safe_error(tmp_path: Path) -> None:
    with pytest.raises(RouterConfigurationError):
        load_router_config(tmp_path / "missing.yaml")
```

- [ ] **Step 3: Run loader tests and verify failure**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_config.py -v`

Expected: FAIL because `load_router_config` does not exist.

- [ ] **Step 4: Implement safe loading and sample configuration**

Read with UTF-8, call `yaml.safe_load`, then `RouterConfig.model_validate`. Catch `OSError`, `yaml.YAMLError`, and Pydantic `ValidationError` and raise `RouterConfigurationError(f"无法加载路由配置: {path}")` using exception chaining. Create `configs/models.yaml` with one enabled Mock primary and one disabled Zhipu backup so the repository default cannot trigger a paid call.

- [ ] **Step 5: Run loader tests**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_config.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit the loader slice**

```powershell
git add app/router/config.py configs/models.yaml tests/router/test_config.py
git commit -m "feat: load model routes from yaml"
```

---

### Task 4: Candidate Resolution

**Files:**
- Create: `app/router/router.py`
- Create: `tests/router/test_router.py`

**Interfaces:**
- Consumes: `RouterConfig`, `ProviderRegistry`, and `ModelRegistry`.
- Produces: `ModelRouter.candidates(capability: str) -> tuple[RouteCandidate, ...]`.

- [ ] **Step 1: Write failing candidate-resolution tests**

Build two `MockProvider` objects and registrations. Verify priority ordering, stable ties, disabled primary selection, capability absence, all disabled state, model-level disabling, and immediate failure for an enabled unknown Provider/model. The central happy-path assertion is:

```python
def test_candidates_are_sorted_by_priority_and_stable_for_ties() -> None:
    router = build_router(
        routes=[
            RouteConfig(channel="backup-a", provider="b", model="m", priority=2),
            RouteConfig(channel="primary", provider="a", model="m", priority=1),
            RouteConfig(channel="backup-b", provider="a", model="m", priority=2),
        ]
    )
    assert [candidate.channel for candidate in router.candidates("text_generation")] == [
        "primary",
        "backup-a",
        "backup-b",
    ]
```

Also assert that a disabled primary produces `backup` first, missing capability raises `CapabilityNotFoundError`, no enabled result raises `NoEnabledRouteError`, and unknown enabled references raise their specific registration errors.

- [ ] **Step 2: Run candidate tests and verify failure**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_router.py -v`

Expected: FAIL because `ModelRouter` does not exist.

- [ ] **Step 3: Implement candidate resolution**

Create `ModelRouter.__init__(config, providers, models)`. In `candidates`, strip and resolve capability, enumerate configured routes, skip route-level disabled entries, resolve Provider before model, skip disabled models, create `RouteCandidate` objects, sort by `(priority, original_index)`, and return a tuple without exposing internal mutable state.

- [ ] **Step 4: Run Router tests**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_router.py -v`

Expected: candidate-resolution tests PASS.

- [ ] **Step 5: Commit candidate resolution**

```powershell
git add app/router/router.py tests/router/test_router.py
git commit -m "feat: resolve ordered model route candidates"
```

---

### Task 5: One-Shot Route Execution and Public API

**Files:**
- Modify: `app/router/router.py`
- Modify: `app/router/__init__.py`
- Modify: `tests/router/test_router.py`

**Interfaces:**
- Consumes: `ChatRequest.model_copy`, `BaseProvider.chat`, and candidate resolution.
- Produces: `await ModelRouter.route(capability: str, request: ChatRequest) -> ChatResponse` and public exports.

- [ ] **Step 1: Write failing one-shot execution tests**

Create a small recording `BaseProvider` test double. Assert that `route()` replaces the model on a copied request, preserves the caller's request, returns the Provider response, and calls only the first candidate. Add a failing Provider double that raises `ProviderTimeoutError`; assert the backup receives zero calls and the exact Provider error propagates.

```python
@pytest.mark.asyncio
async def test_route_calls_only_first_candidate_with_selected_model() -> None:
    request = ChatRequest(
        model="business-placeholder",
        messages=[ChatMessage(role="user", content="hello")],
    )
    response = await router.route("text_generation", request)
    assert primary.requests[0].model == "primary-model"
    assert request.model == "business-placeholder"
    assert response.provider == "primary"
    assert backup.requests == []


@pytest.mark.asyncio
async def test_route_does_not_fallback_after_provider_error() -> None:
    with pytest.raises(ProviderTimeoutError):
        await router.route("text_generation", request)
    assert backup.requests == []
```

- [ ] **Step 2: Run focused execution tests and verify failure**

Run: `.\.venv\Scripts\python -m pytest tests/router/test_router.py -v`

Expected: FAIL because `ModelRouter.route` is not implemented.

- [ ] **Step 3: Implement one-shot execution and public exports**

Implement:

```python
async def route(self, capability: str, request: ChatRequest) -> ChatResponse:
    candidate = self.candidates(capability)[0]
    routed_request = request.model_copy(update={"model": candidate.model})
    return await candidate.provider.chat(routed_request)
```

Export schemas, registries, loader, Router, and every Router error from `app/router/__init__.py` using an explicit `__all__`.

- [ ] **Step 4: Run all Router tests**

Run: `.\.venv\Scripts\python -m pytest tests/router -v`

Expected: all Router tests PASS.

- [ ] **Step 5: Commit execution and exports**

```powershell
git add app/router/router.py app/router/__init__.py tests/router/test_router.py
git commit -m "feat: execute highest priority route once"
```

---

### Task 6: Full Regression and Phase 2 Acceptance

**Files:**
- Modify only files required to correct failures caused by Phase 2 changes.

**Interfaces:**
- Consumes: the complete Phase 0–2 test suite and compiled application package.
- Produces: evidence that Phase 2 satisfies its acceptance criteria without regressing earlier phases.

- [ ] **Step 1: Run the complete test suite**

Run: `.\.venv\Scripts\python -m pytest -v`

Expected: all tests PASS and no real network call occurs.

- [ ] **Step 2: Compile application modules**

Run: `.\.venv\Scripts\python -m compileall -q app`

Expected: exit code 0 with no output.

- [ ] **Step 3: Inspect tracked changes for secrets and scope**

Run: `git diff --check HEAD~5..HEAD` and `git status --short`

Expected: no whitespace errors, no API key, and only intended Phase 2 files are committed; pre-existing user changes remain untouched.

- [ ] **Step 4: Commit any narrowly scoped verification correction**

If verification required a correction, stage only the affected Phase 2 files and commit with `fix: complete phase 2 routing verification`. If no correction was required, do not create an empty commit.
